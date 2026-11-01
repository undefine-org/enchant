package io.beamlisp.android

import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.InputStreamReader
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.SimpleFileVisitor
import java.nio.file.FileVisitResult
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.BasicFileAttributes
import java.security.DigestInputStream
import java.security.MessageDigest
import java.util.zip.ZipInputStream

/** Install signed APK runtime files before ERTS starts. Application data is never
 * inferred from an otp/ directory: only an unchanged receipt-owned file may be
 * pruned. This shares otp/.bl-runtime-files with the Source push installer.
 * No Android dependencies; the same installer is exercised by JVM tests.
 */
object BlRuntime {
    private const val RECEIPT = ".bl-runtime-files"
    private const val REQUIRED = "lib/beam_lisp-0.1.0/ebin/beam_lisp.app"
    private const val MAX_FILES = 100000
    private const val MAX_BYTES = 4L * 1024 * 1024 * 1024
    private val hashPattern = Regex("[a-f0-9]{64}")

    private fun exists(file: File) = Files.exists(file.toPath(), LinkOption.NOFOLLOW_LINKS)
    private fun regular(file: File) = Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS)
    private fun directory(file: File) = Files.isDirectory(file.toPath(), LinkOption.NOFOLLOW_LINKS)
    private fun noLink(file: File) {
        require(!Files.isSymbolicLink(file.toPath())) { "Runtime path is a symbolic link: $file" }
    }
    private fun relative(name: String): String {
        require(name.isNotEmpty() && name.length <= 4096 &&
            name.none { it == '\\' || it == '\u0000' || it == '\n' || it == '\r' || it == ':' }) {
            "Invalid runtime path"
        }
        val parts = name.split('/')
        require(parts.size <= 128 && parts.none { it.isEmpty() || it == "." || it == ".." }) {
            "Invalid runtime path"
        }
        require(name != RECEIPT && !name.startsWith("$RECEIPT/")) { "Reserved runtime receipt path" }
        return name
    }
    private fun target(root: File, name: String): File {
        var parent = root
        noLink(parent)
        val parts = relative(name).split('/')
        for (part in parts.dropLast(1)) {
            parent = File(parent, part)
            noLink(parent)
            require(!exists(parent) || directory(parent)) { "Runtime parent is not a directory: $parent" }
        }
        return File(parent, parts.last()).also { noLink(it) }
    }
    private fun mkdir(file: File) {
        noLink(file)
        check(directory(file) || file.mkdir()) { "Cannot create runtime directory: $file" }
    }
    private fun parents(root: File, name: String) {
        var at = root
        for (part in relative(name).split('/').dropLast(1)) {
            at = File(at, part)
            mkdir(at)
        }
    }
    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }
    private fun digest(file: File): String {
        val hash = MessageDigest.getInstance("SHA-256")
        Files.newInputStream(file.toPath(), LinkOption.NOFOLLOW_LINKS).use { input ->
            val bytes = ByteArray(8192)
            while (true) {
                val size = input.read(bytes)
                if (size == -1) break
                hash.update(bytes, 0, size)
            }
        }
        return hex(hash.digest())
    }
    private fun receipt(file: File): Map<String, String>? {
        noLink(file)
        if (!exists(file)) return null
        require(regular(file) && file.length() <= 16L * 1024 * 1024) { "Invalid runtime receipt" }
        val files = LinkedHashMap<String, String>()
        val decoder = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
        InputStreamReader(Files.newInputStream(file.toPath(), LinkOption.NOFOLLOW_LINKS), decoder)
            .buffered().useLines { lines ->
            lines.forEach { line ->
                require(line.length >= 67 && line.substring(64, 66) == "  " &&
                    hashPattern.matches(line.substring(0, 64))) { "Invalid runtime receipt" }
                val path = relative(line.substring(66))
                require(files.put(path, line.substring(0, 64)) == null && files.size <= MAX_FILES) {
                    "Duplicate or excessive runtime receipt entries"
                }
            }
        }
        return files
    }
    private class Backups(private val root: File) {
        private var attempt: File? = null
        fun preserve(file: File, name: String) {
            val parent = File(root, ".bl-runtime-backups")
            mkdir(parent)
            val destination = attempt ?: Files.createTempDirectory(parent.toPath(), "install-").toFile().also {
                attempt = it
            }
            // Backup names start with otp/ or metadata/ and have no aliases.
            parents(destination, name)
            val copy = target(destination, name)
            check(copy.createNewFile()) { "Cannot preserve previous runtime file" }
            Files.newInputStream(file.toPath(), LinkOption.NOFOLLOW_LINKS).use { input ->
                FileOutputStream(copy).use { output -> input.copyTo(output); output.fd.sync() }
            }
        }
    }
    private fun atomic(file: File, content: String) {
        noLink(file)
        require(!exists(file) || regular(file)) { "Runtime metadata is not a regular file" }
        val pending = Files.createTempFile(file.parentFile.toPath(), ".bl-runtime-", ".next").toFile()
        try {
            FileOutputStream(pending).use { output ->
                output.write(content.toByteArray(Charsets.UTF_8)); output.fd.sync()
            }
            noLink(file)
            require(!exists(file) || regular(file)) { "Runtime metadata changed type" }
            Files.move(pending.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING)
        } finally {
            Files.deleteIfExists(pending.toPath())
        }
    }
    private fun removeOwnedStage(stage: File) {
        // This attempt exclusively created the directory. Never follow links,
        // or delete legacy fixed .bl-runtime-install/.bl-runtime-previous trees.
        Files.walkFileTree(stage.toPath(), object : SimpleFileVisitor<Path>() {
            override fun visitFile(file: Path, attrs: BasicFileAttributes): FileVisitResult {
                Files.deleteIfExists(file)
                return FileVisitResult.CONTINUE
            }
            override fun postVisitDirectory(dir: Path, error: java.io.IOException?): FileVisitResult {
                if (error != null) throw error
                Files.deleteIfExists(dir)
                return FileVisitResult.CONTINUE
            }
        })
    }

    @Synchronized
    fun install(filesDir: File, expectedDigest: String, openArchive: () -> InputStream) {
        require(hashPattern.matches(expectedDigest)) { "Invalid runtime digest" }
        val root = filesDir.canonicalFile
        check(directory(root)) { "Runtime files directory is unavailable" }
        val lock = File(root, ".bl-runtime-install.lock")
        try {
            Files.createDirectory(lock.toPath())
        } catch (busy: java.nio.file.FileAlreadyExistsException) {
            throw IllegalStateException("Runtime install is already owned; a stale lock needs explicit recovery", busy)
        }
        var failure: Throwable? = null
        try {
            installLocked(root, expectedDigest, openArchive)
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            // Never recursively remove a lock or steal one left by another attempt.
            try { Files.delete(lock.toPath()) } catch (cleanup: Exception) {
                if (failure != null) failure.addSuppressed(cleanup) else throw cleanup
            }
        }
    }

    private fun installLocked(root: File, expectedDigest: String, openArchive: () -> InputStream) {
        val runtime = File(root, "otp")
        noLink(runtime)
        require(!exists(runtime) || directory(runtime)) { "Runtime root is not a directory" }
        val marker = File(root, ".bl-runtime")
        noLink(marker)
        require(!exists(marker) || regular(marker)) { "Runtime marker is not a regular file" }
        val index = File(runtime, RECEIPT)
        val previous = receipt(index)
        val required = target(runtime, REQUIRED)
        if (regular(marker) && marker.length() <= 128 && marker.readText().trim() == expectedDigest &&
            previous?.containsKey(REQUIRED) == true && regular(required) &&
            digest(required) == previous[REQUIRED]) return

        val stage = Files.createTempDirectory(root.toPath(), ".bl-runtime-install-").toFile()
        val candidate = File(stage, "otp")
        var failure: Throwable? = null
        try {
            check(candidate.mkdir()) { "Cannot create runtime staging directory" }
            val archiveHash = MessageDigest.getInstance("SHA-256")
            val incoming = LinkedHashMap<String, String>()
            val directories = HashSet<String>()
            openArchive().use { raw ->
                val checked = DigestInputStream(raw, archiveHash)
                val zip = ZipInputStream(checked)
                val seen = HashSet<String>()
                var total = 0L
                try {
                    while (true) {
                        val entry = zip.nextEntry ?: break
                        require(entry.name.startsWith("otp/")) { "Runtime entry outside otp/" }
                        val path = entry.name.removePrefix("otp/").removeSuffix(if (entry.isDirectory) "/" else "")
                        if (path.isEmpty() && entry.isDirectory) {
                            require(seen.add("")) { "Duplicate runtime entry" }
                            zip.closeEntry(); continue
                        }
                        // A supplied index is not an ownership grant. Derive it
                        // from the checksum-verified ZIP's actual regular files.
                        val suppliedReceipt = path == RECEIPT && !entry.isDirectory
                        if (!suppliedReceipt) relative(path)
                        require(seen.add(path) && seen.size <= MAX_FILES) { "Duplicate runtime entry" }
                        val output = if (entry.isDirectory || suppliedReceipt) null else target(candidate, path)
                        if (entry.isDirectory) {
                            require(zip.read() == -1) { "Runtime directory contains file data" }
                            parents(candidate, "$path/placeholder")
                            directories.add(path)
                        } else {
                            if (output != null) parents(candidate, path)
                            val hash = MessageDigest.getInstance("SHA-256")
                            val stream = output?.let { FileOutputStream(it) }
                            try {
                                val bytes = ByteArray(8192)
                                while (true) {
                                    val size = zip.read(bytes)
                                    if (size == -1) break
                                    total += size
                                    require(total <= MAX_BYTES) { "Runtime bundle exceeds byte limit" }
                                    stream?.write(bytes, 0, size); hash.update(bytes, 0, size)
                                }
                                stream?.fd?.sync()
                            } finally { stream?.close() }
                            if (output != null) incoming[path] = hex(hash.digest())
                        }
                        zip.closeEntry()
                    }
                    // ZipInputStream need not consume the central directory.
                    val remainder = ByteArray(8192)
                    while (checked.read(remainder) != -1) { }
                    check(hex(archiveHash.digest()) == expectedDigest) { "Runtime checksum mismatch" }
                } finally { zip.close() }
            }
            check(incoming.containsKey(REQUIRED)) { "Incomplete runtime bundle" }
            // Refuse all known path/type conflicts before changing active files.
            for (path in incoming.keys) {
                val file = target(runtime, path)
                require(!exists(file) || regular(file)) { "Runtime file conflicts with a directory: $file" }
            }
            for (path in directories) {
                val file = target(runtime, path)
                require(!exists(file) || directory(file)) { "Runtime directory conflicts with a file: $file" }
            }
            mkdir(runtime)
            val backups = Backups(root)
            for (path in directories.sortedBy { it.count { char -> char == '/' } }) {
                parents(runtime, "$path/placeholder")
            }
            for (path in incoming.keys) {
                parents(runtime, path)
                val file = target(runtime, path)
                require(!exists(file) || regular(file)) { "Runtime destination changed type" }
                if (regular(file) && (previous?.get(path) == null || digest(file) != previous[path])) {
                    backups.preserve(file, "otp/$path")
                }
                Files.move(target(candidate, path).toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING)
            }
            for ((path, hash) in previous.orEmpty()) {
                if (incoming.containsKey(path)) continue
                val file = try { target(runtime, path) } catch (_: IllegalArgumentException) { continue }
                if (regular(file) && digest(file) == hash) Files.delete(file.toPath())
            }
            // Commit ownership first, APK version last. Interrupted publication
            // therefore retries; user backups are retained across every retry.
            atomic(index, incoming.toSortedMap().entries.joinToString("") { "${it.value}  ${it.key}\n" })
            if (regular(marker) && (marker.length() > 128 || marker.readText() != expectedDigest)) {
                backups.preserve(marker, "metadata/.bl-runtime")
            }
            atomic(marker, expectedDigest)
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            try { removeOwnedStage(stage) } catch (cleanup: Exception) {
                if (failure != null) failure.addSuppressed(cleanup) else throw cleanup
            }
        }
    }
}
