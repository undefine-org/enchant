/* Synthetic-fixture fault injector only. Never loaded by the SDK itself.
 * Stop the entire process AFTER a successful real fsync at a named boundary.
 * The external controller must observe the acknowledgement before killing it.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int (*real_sync)(int);
static const char *job, *destination, *boundary, *ack;
static atomic_flag stopped = ATOMIC_FLAG_INIT;
__attribute__((constructor)) static void initialize(void) {
    real_sync = dlsym(RTLD_NEXT, "fsync");
    job = getenv("DATOM_CRASH_JOB"); destination = getenv("DATOM_CRASH_DESTINATION");
    boundary = getenv("DATOM_CRASH_BOUNDARY"); ack = getenv("DATOM_CRASH_ACK");
}
static int has(const char *bytes, size_t n, const char *needle) {
    return memmem(bytes, n, needle, strlen(needle)) != NULL;
}
static int phase(const char *bytes, size_t n, const char *wanted) {
    /* Match an ETF atom key/value pair, never a fixture path containing the
     * same word. Default ETF permits either small or full UTF8/Latin1 atoms. */
    const unsigned char *p = (const unsigned char *)bytes;
    for (size_t i = 0; i + 7 < n; i++) {
        size_t key = i;
        if (p[key] == 119) { if (p[key + 1] != 5) continue; key += 2; }
        else if (p[key] == 100 || p[key] == 118) {
            if (p[key + 1] || p[key + 2] != 5) continue;
            key += 3;
        } else continue;
        if (key + 5 >= n || memcmp(p + key, "phase", 5)) continue;
        size_t value = key + 5, length;
        if (p[value] == 119) { if (value + 2 > n) continue; length = p[value + 1]; value += 2; }
        else if (p[value] == 100 || p[value] == 118) {
            if (value + 3 > n) continue;
            length = ((size_t)p[value + 1] << 8) | p[value + 2]; value += 3;
        } else continue;
        if (value + length <= n && length == strlen(wanted) && !memcmp(p + value, wanted, length)) return 1;
    }
    return 0;
}
int fsync(int fd) {
    int result = real_sync(fd);
    if (result || !job || !destination || !boundary || !ack) return result;
    char descriptor[64], path[PATH_MAX], control[PATH_MAX];
    snprintf(descriptor, sizeof descriptor, "/proc/self/fd/%d", fd);
    ssize_t length = readlink(descriptor, path, sizeof path - 1);
    if (length < 0) return result;
    path[length] = 0;
    /* Ignore all compiler/cache and unrelated engine fsyncs. */
    size_t root_length = strlen(job);
    if (strncmp(path, job, root_length) || (path[root_length] && path[root_length] != '/')) return result;
    snprintf(control, sizeof control, "%s/job.etf", job);
    int record = open(control, O_RDONLY | O_CLOEXEC);
    if (record < 0) return result;
    /* Fixture journals are tiny. Oversize/short/changed reads do not arm. */
    char bytes[65536]; ssize_t n = read(record, bytes, sizeof bytes); close(record);
    if (n <= 0 || (size_t)n == sizeof bytes) return result;
    int trigger = 0;
    if (!strcmp(boundary, "converting")) trigger = !strcmp(path, job) && phase(bytes, n, "converting");
    if (!strcmp(boundary, "store-complete"))
        trigger = !strcmp(path, job) && phase(bytes, n, "converting") && has(bytes, n, "basis");
    if (!strcmp(boundary, "ready")) {
        snprintf(control, sizeof control, "%s/target/.bl-generation", job);
        trigger = access(control, F_OK) == 0;
    }
    if (!strcmp(boundary, "renamed")) {
        snprintf(control, sizeof control, "%s/.bl-generation", destination);
        trigger = !strcmp(path, job) && access(control, F_OK) == 0;
    }
    if (!trigger || atomic_flag_test_and_set(&stopped)) return result;
    int output = open(ack, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (output < 0 || write(output, boundary, strlen(boundary)) != (ssize_t)strlen(boundary)) _exit(96);
    close(output);
    /* SIGSTOP stops all BEAM threads; no application cleanup can run. */
    raise(SIGSTOP);
    _exit(97); /* Continuing an injected victim is always an invalid check. */
}
