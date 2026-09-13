#define _GNU_SOURCE
#include <dlfcn.h>
#include <unistd.h>
#include <sys/auxv.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>

/* This scratch runtime has no procfs. Supply only this process's executable
   path from the ELF auxiliary vector; leave all other filesystem calls alone. */
ssize_t readlink(const char *path, char *buf, size_t size) {
    ssize_t (*original)(const char *, char *, size_t) = dlsym(RTLD_NEXT, "readlink");
    ssize_t result = original(path, buf, size);
    if (result >= 0 || errno != ENOENT) return result;
    char own_proc_path[80];
    snprintf(own_proc_path, sizeof own_proc_path, "/proc/%d/exe", (int)getpid());
    if (strcmp(path, own_proc_path) != 0) return result;
    const char *exe = (const char *)getauxval(AT_EXECFN);
    if (!exe || exe[0] != '/') return result;
    size_t count = strlen(exe);
    if (count > size) count = size;
    memcpy(buf, exe, count);
    return (ssize_t)count;
}
