package io.beamlisp.android

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class BlRuntimeTest {
    private val app = "otp/lib/beam_lisp-0.1.0/ebin/beam_lisp.app"
    private fun archive(vararg entries: Pair<String, String>): ByteArray {
        val output = ByteArrayOutputStream()
        ZipOutputStream(output).use { zip ->
            for ((name, text) in entries) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(text.toByteArray())
                zip.closeEntry()
            }
        }
        return output.toByteArray()
    }
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }
    private fun install(root: java.io.File, bytes: ByteArray) =
        BlRuntime.install(root, digest(bytes)) { ByteArrayInputStream(bytes) }
    private fun fails(action: () -> Unit) {
        try { action(); fail("Expected installation failure") } catch (_: Exception) { }
    }
    @Test fun freshInstallAndFastRelaunch() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            val bytes = archive(app to "runtime", "otp/pocket/boot.beam" to "app")
            install(root, bytes)
            assertEquals("app", root.resolve("otp/pocket/boot.beam").readText())
            BlRuntime.install(root, digest(bytes)) { error("Already installed: must not open ZIP") }
        } finally { root.deleteRecursively() }
    }
    @Test fun upgradePreservesSettingsAndRemovesOldCode() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            install(root, archive(app to "v1", "otp/old.beam" to "old"))
            root.resolve("pocket-origin").writeText("https://host.tail.ts.net")
            install(root, archive(app to "v2", "otp/new.beam" to "new"))
            assertFalse(root.resolve("otp/old.beam").exists())
            assertEquals("v2", root.resolve(app).readText())
            assertEquals("https://host.tail.ts.net", root.resolve("pocket-origin").readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun checksumFailureKeepsPreviousRuntime() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            install(root, archive(app to "good"))
            val bytes = archive(app to "bad")
            fails { BlRuntime.install(root, "0".repeat(64)) { ByteArrayInputStream(bytes) } }
            assertEquals("good", root.resolve(app).readText())
            assertFalse(root.resolve(".bl-runtime-install").exists())
        } finally { root.deleteRecursively() }
    }
    @Test fun incompleteBundleKeepsPreviousRuntime() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            install(root, archive(app to "good"))
            fails { install(root, archive("otp/incomplete" to "bad")) }
            assertEquals("good", root.resolve(app).readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun rejectsEscapingEntries() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            fails { install(root, archive("otp/../../escaped" to "bad", app to "bad")) }
            assertFalse(root.resolve("otp").exists())
        } finally { root.deleteRecursively() }
    }
    @Test fun rejectsAliasedEntries() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            fails { install(root, archive(app to "one", "otp/./lib/beam_lisp-0.1.0/ebin/beam_lisp.app" to "two")) }
            assertFalse(root.resolve("otp").exists())
        } finally { root.deleteRecursively() }
    }
    @Test fun preservesLegacyStagingAndBackup() {
        val root = Files.createTempDirectory("runtime-test").toFile()
        try {
            root.resolve(".bl-runtime-install").mkdirs()
            root.resolve(".bl-runtime-install/partial").writeText("interrupted")
            root.resolve(".bl-runtime-previous").mkdirs()
            root.resolve(".bl-runtime-previous/user.db").writeText("legacy data")
            install(root, archive(app to "complete"))
            assertEquals("complete", root.resolve(app).readText())
            assertEquals("legacy data", root.resolve(".bl-runtime-previous/user.db").readText())
            assertEquals("interrupted", root.resolve(".bl-runtime-install/partial").readText())
        } finally { root.deleteRecursively() }
    }

    private fun backups(root: File, content: String): List<File> =
        root.resolve(".bl-runtime-backups").takeIf { it.isDirectory }?.walkTopDown()
            ?.filter { it.isFile && it.readText() == content }?.toList().orEmpty()
    private fun receipt(root: File) = root.resolve("otp/.bl-runtime-files")
    private fun write(root: File, path: String, text: String) {
        root.resolve(path).also { it.parentFile.mkdirs() }.writeText(text)
    }

    @Test fun preservesForeignRelativeDatomDataOnUpgrade() {
        val root = Files.createTempDirectory("runtime-data").toFile()
        try {
            install(root, archive(app to "v1", "otp/pocket/old.beam" to "old code"))
            write(root, "otp/pocket/data/people.fjall/keyspace", "application database")
            write(root, "otp/lib/private-data/notes", "foreign notes")
            install(root, archive(app to "v2", "otp/pocket/new.beam" to "new code"))
            assertEquals("application database", root.resolve("otp/pocket/data/people.fjall/keyspace").readText())
            assertEquals("foreign notes", root.resolve("otp/lib/private-data/notes").readText())
            assertFalse(root.resolve("otp/pocket/old.beam").exists())
            assertTrue(root.resolve("otp/pocket/data").isDirectory)
        } finally { root.deleteRecursively() }
    }
    @Test fun changedFormerlyOwnedFilesArePreservedAndNotReclaimed() {
        val root = Files.createTempDirectory("runtime-modified").toFile()
        try {
            install(root, archive(app to "v1", "otp/old.beam" to "old code"))
            root.resolve("otp/old.beam").writeText("user bytes")
            install(root, archive(app to "v2"))
            install(root, archive(app to "v3"))
            assertEquals("user bytes", root.resolve("otp/old.beam").readText())
            assertFalse(receipt(root).readText().contains("old.beam"))
        } finally { root.deleteRecursively() }
    }
    @Test fun collisionsBackUpUnownedAndModifiedFiles() {
        val root = Files.createTempDirectory("runtime-collision").toFile()
        try {
            install(root, archive(app to "v1", "otp/changed.beam" to "original"))
            write(root, "otp/data/collision", "foreign database bytes")
            root.resolve("otp/changed.beam").writeText("modified application bytes")
            install(root, archive(app to "v2", "otp/data/collision" to "runtime file", "otp/changed.beam" to "new code"))
            assertEquals("runtime file", root.resolve("otp/data/collision").readText())
            assertEquals("new code", root.resolve("otp/changed.beam").readText())
            assertEquals(1, backups(root, "foreign database bytes").size)
            assertEquals(1, backups(root, "modified application bytes").size)
            install(root, archive(app to "v3"))
            assertEquals(1, backups(root, "foreign database bytes").size)
            assertEquals(1, backups(root, "modified application bytes").size)
        } finally { root.deleteRecursively() }
    }
    @Test fun legacyWithoutReceiptPreservesUnknownContentAndBacksUpCollisions() {
        val root = Files.createTempDirectory("runtime-legacy").toFile()
        try {
            write(root, app, "legacy runtime")
            write(root, "otp/lib/legacy/user.db", "legacy database")
            write(root, "otp/new.beam", "legacy collision")
            install(root, archive(app to "new runtime", "otp/new.beam" to "new code"))
            assertEquals("legacy database", root.resolve("otp/lib/legacy/user.db").readText())
            assertEquals(1, backups(root, "legacy runtime").size)
            assertEquals(1, backups(root, "legacy collision").size)
            assertTrue(receipt(root).isFile)
        } finally { root.deleteRecursively() }
    }
    @Test fun legacyMatchingDigestStillCreatesGenuineOwnershipReceipt() {
        val root = Files.createTempDirectory("runtime-legacy-marker").toFile()
        try {
            val bytes = archive(app to "runtime")
            write(root, app, "runtime")
            write(root, ".bl-runtime", digest(bytes))
            write(root, "otp/data.db", "keep")
            var opened = 0
            BlRuntime.install(root, digest(bytes)) { opened++; ByteArrayInputStream(bytes) }
            assertEquals(1, opened)
            assertEquals("keep", root.resolve("otp/data.db").readText())
            assertTrue(receipt(root).readText().contains(app.removePrefix("otp/")))
        } finally { root.deleteRecursively() }
    }
    @Test fun suppliedReceiptDoesNotClaimUnknownFiles() {
        val root = Files.createTempDirectory("runtime-index").toFile()
        try {
            write(root, "otp/user.db", "keep")
            val falseClaim = digest("keep".toByteArray()) + "  user.db\n"
            install(root, archive(app to "v1", "otp/.bl-runtime-files" to falseClaim))
            install(root, archive(app to "v2"))
            assertEquals("keep", root.resolve("otp/user.db").readText())
            assertFalse(receipt(root).readText().contains("user.db"))
        } finally { root.deleteRecursively() }
    }
    @Test fun readsSharedSha256ReceiptWithSpacesAndPrunesOnlyUnchangedOwnedFiles() {
        val root = Files.createTempDirectory("runtime-shared-index").toFile()
        try {
            write(root, app, "old app")
            write(root, "otp/lib/a file.beam", "owned")
            write(root, "otp/user.db", "foreign")
            receipt(root).writeText(digest("old app".toByteArray()) + "  " + app.removePrefix("otp/") + "\n" +
                digest("owned".toByteArray()) + "  lib/a file.beam\n")
            install(root, archive(app to "new app"))
            assertFalse(root.resolve("otp/lib/a file.beam").exists())
            assertEquals("foreign", root.resolve("otp/user.db").readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun invalidExistingReceiptRefusesWithoutChangingData() {
        val root = Files.createTempDirectory("runtime-bad-index").toFile()
        try {
            install(root, archive(app to "old"))
            write(root, "otp/user.db", "keep")
            receipt(root).writeText("0".repeat(64) + "  ../user.db\n")
            fails { install(root, archive(app to "new")) }
            assertEquals("old", root.resolve(app).readText())
            assertEquals("keep", root.resolve("otp/user.db").readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun rejectsStaticAndDanglingSymlinkDestinations() {
        for (dangling in listOf(false, true)) {
            val root = Files.createTempDirectory("runtime-link").toFile()
            try {
                val outside = root.resolve("outside")
                if (!dangling) { outside.mkdirs(); outside.resolve("secret").writeText("outside") }
                root.resolve("otp").mkdir()
                Files.createSymbolicLink(root.resolve("otp/lib").toPath(), outside.toPath())
                fails { install(root, archive(app to "bad")) }
                assertTrue(Files.isSymbolicLink(root.resolve("otp/lib").toPath()))
                if (!dangling) assertEquals("outside", outside.resolve("secret").readText())
                else assertFalse(outside.exists())
            } finally { root.deleteRecursively() }
        }
    }
    @Test fun rejectsSymlinkReceiptWithoutFollowingIt() {
        val root = Files.createTempDirectory("runtime-index-link").toFile()
        try {
            write(root, app, "old")
            val outside = root.resolve("outside")
            outside.writeText("keep")
            Files.createSymbolicLink(receipt(root).toPath(), outside.toPath())
            fails { install(root, archive(app to "new")) }
            assertEquals("keep", outside.readText())
            assertEquals("old", root.resolve(app).readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun directoryCollisionRefusesBeforeReplacingRuntimeFiles() {
        val root = Files.createTempDirectory("runtime-dir-collision").toFile()
        try {
            install(root, archive(app to "old"))
            write(root, "otp/path/user.db", "directory database")
            fails { install(root, archive(app to "new", "otp/path" to "file")) }
            assertEquals("old", root.resolve(app).readText())
            assertEquals("directory database", root.resolve("otp/path/user.db").readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun formerlyOwnedFileChangedToDirectorySurvivesPruning() {
        val root = Files.createTempDirectory("runtime-owned-dir").toFile()
        try {
            install(root, archive(app to "old", "otp/old" to "code"))
            root.resolve("otp/old").delete()
            write(root, "otp/old/user.db", "directory database")
            install(root, archive(app to "new"))
            assertEquals("directory database", root.resolve("otp/old/user.db").readText())
        } finally { root.deleteRecursively() }
    }
    @Test fun rejectsNonCanonicalZipPathsAndDirectoryPayloads() {
        for (path in listOf("otp//bad", "otp/./bad", "otp/a/../bad", "otp/a\\bad", "outside", "/otp/bad", "otp/C:/bad", "otp/data/")) {
            val root = Files.createTempDirectory("runtime-path").toFile()
            try {
                install(root, archive(app to "old"))
                fails { install(root, archive(app to "new", path to "payload")) }
                assertEquals("old", root.resolve(app).readText())
            } finally { root.deleteRecursively() }
        }
    }
    @Test fun interruptedReadKeepsDataAndRetriesWithFreshOwnedStage() {
        val root = Files.createTempDirectory("runtime-interrupt").toFile()
        try {
            install(root, archive(app to "old"))
            write(root, "otp/user.db", "keep")
            fails { BlRuntime.install(root, "0".repeat(64)) { throw IOException("interrupted") } }
            assertEquals("old", root.resolve(app).readText())
            assertEquals("keep", root.resolve("otp/user.db").readText())
            install(root, archive(app to "new"))
            assertEquals("new", root.resolve(app).readText())
            assertEquals("keep", root.resolve("otp/user.db").readText())
            assertFalse(root.listFiles()!!.any { it.name.startsWith(".bl-runtime-install-") })
        } finally { root.deleteRecursively() }
    }
    @Test fun receiptPublishFailurePreservesUserBackupAndRetries() {
        val root = Files.createTempDirectory("runtime-receipt-failure").toFile()
        val otp = root.resolve("otp")
        try {
            val old = archive(app to "old")
            install(root, old)
            write(root, "otp/user/data", "user before receipt failure")
            val before = receipt(root).readText()
            val bytes = archive(app to "new", "otp/user/data" to "runtime data")
            fails { BlRuntime.install(root, digest(bytes)) {
                check(otp.setWritable(false, false)); check(!otp.canWrite())
                ByteArrayInputStream(bytes)
            } }
            check(otp.setWritable(true, true))
            assertEquals(before, receipt(root).readText())
            assertEquals(digest(old), root.resolve(".bl-runtime").readText())
            assertEquals(1, backups(root, "user before receipt failure").size)
            install(root, bytes)
            assertEquals("runtime data", root.resolve("otp/user/data").readText())
            assertEquals(1, backups(root, "user before receipt failure").size)
        } finally { otp.setWritable(true, true); root.deleteRecursively() }
    }
    @Test fun markerPublishFailureLeavesOldMarkerAndKeepsUserBackupOnRetry() {
        val root = Files.createTempDirectory("runtime-marker-failure").toFile()
        try {
            val old = archive(app to "old")
            install(root, old)
            root.resolve(".bl-runtime-backups").mkdir()
            write(root, "otp/user/data", "user before marker failure")
            val bytes = archive(app to "new", "otp/user/data" to "runtime data")
            fails { BlRuntime.install(root, digest(bytes)) {
                check(root.setWritable(false, false)); check(!root.canWrite())
                ByteArrayInputStream(bytes)
            } }
            check(root.setWritable(true, true))
            assertEquals(digest(old), root.resolve(".bl-runtime").readText())
            assertEquals(1, backups(root, "user before marker failure").size)
            // Permission loss also prevented release of this attempt's empty
            // lock. Recover explicitly; a new installer must not steal it.
            val lock = root.resolve(".bl-runtime-install.lock")
            assertTrue(lock.isDirectory)
            assertEquals(0, lock.list()!!.size)
            assertTrue(lock.delete())
            install(root, bytes)
            assertEquals(digest(bytes), root.resolve(".bl-runtime").readText())
            assertEquals(1, backups(root, "user before marker failure").size)
        } finally { root.setWritable(true, true); root.deleteRecursively() }
    }

    @Test fun existingOrStaleLockIsNeverStolen() {
        val root = Files.createTempDirectory("runtime-lock").toFile()
        try {
            val lock = root.resolve(".bl-runtime-install.lock")
            lock.mkdir()
            lock.resolve("unknown").writeText("preserve")
            var opened = false
            val bytes = archive(app to "new")
            fails { BlRuntime.install(root, digest(bytes)) { opened = true; ByteArrayInputStream(bytes) } }
            assertFalse(opened)
            assertEquals("preserve", lock.resolve("unknown").readText())
            assertFalse(root.resolve("otp").exists())
        } finally { root.deleteRecursively() }
    }
    @Test fun competingAttemptCannotPublishAndOwnerReleasesOnlyItsLock() {
        val root = Files.createTempDirectory("runtime-competing").toFile()
        try {
            val bytes = archive(app to "owner")
            BlRuntime.install(root, digest(bytes)) {
                fails { install(root, archive(app to "competitor")) }
                ByteArrayInputStream(bytes)
            }
            assertEquals("owner", root.resolve(app).readText())
            assertFalse(root.resolve(".bl-runtime-install.lock").exists())
        } finally { root.deleteRecursively() }
    }
}
