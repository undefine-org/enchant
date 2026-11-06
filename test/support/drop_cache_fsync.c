/* Synthetic cache fixture only: stop at real file/tree/publication boundaries.
 * No SDK or production database loads this test injector. */
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
static int (*real_rename)(const char *, const char *);
static const char *store, *destination, *boundary, *ack;
static atomic_flag stopped = ATOMIC_FLAG_INIT;
__attribute__((constructor)) static void initialize(void) {
    real_sync = dlsym(RTLD_NEXT, "fsync"); real_rename = dlsym(RTLD_NEXT, "rename");
    store = getenv("DROP_CACHE_STORE"); destination = getenv("DROP_CACHE_DESTINATION");
    boundary = getenv("DROP_CACHE_BOUNDARY"); ack = getenv("DROP_CACHE_ACK");
}
static void stop_victim(void) {
    if (atomic_flag_test_and_set(&stopped)) return;
    int fd = open(ack, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, boundary, strlen(boundary)) != (ssize_t)strlen(boundary)) _exit(96);
    close(fd); raise(SIGSTOP); _exit(97);
}
int fsync(int fd) {
    int result = real_sync(fd);
    if (result || !store || !destination || !boundary || !ack) return result;
    char descriptor[64], path[PATH_MAX];
    snprintf(descriptor, sizeof descriptor, "/proc/self/fd/%d", fd);
    ssize_t length = readlink(descriptor, path, sizeof path - 1);
    if (length < 0) return result;
    path[length] = 0;
    size_t prefix = strlen(store);
    if (strncmp(path, store, prefix) || (path[prefix] && path[prefix] != '/')) return result;
    const char *leaf = path[prefix] ? path + prefix + 1 : "";
    int staging = strstr(leaf, ".tmp-") != NULL;
    if ((!strcmp(boundary, "file-synced") && staging && strstr(leaf, "/releases/start_erl.data")) ||
        (!strcmp(boundary, "tree-synced") && staging && !strchr(leaf, '/')) ||
        (!strcmp(boundary, "published") && !strcmp(path, store) && access(destination, F_OK) == 0)) stop_victim();
    return result;
}
int rename(const char *from, const char *to) {
    int result = real_rename(from, to);
    if (!result && destination && boundary && ack && !strcmp(boundary, "renamed") &&
        !strcmp(to, destination) && strstr(from, ".tmp-")) stop_victim();
    return result;
}
