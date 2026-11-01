#!/system/bin/sh
# Run as the application UID, with its files directory as $2. Only an unchanged
# file in the previous receipt is eligible for deletion. Unknown/changed files
# are data; conflicting replacements retain their original bytes in a backup.
set -eu
archive=$1
files=$2
mkdir -p "$files"
cd "$files"
lock=.bl-runtime-install.lock
mkdir "$lock"
stage=
trap 'test -z "$stage" || rm -rf "$stage"; rmdir "$lock"' EXIT
trap 'exit 1' HUP INT TERM
stage=$(mktemp -d .bl-runtime-install.XXXXXX)
backup=".bl-runtime-preserved.${stage##*.}"
backup_created=0
receipt=.bl-runtime-files
test ! -L otp
test ! -L "otp/$receipt"
if test -e "otp/$receipt"; then test -f "otp/$receipt"; fi
mkdir -p otp

lexical_path() {
    case "$1" in ''|/*|*//*|../*|*/../*|*/..|..|./*|*/./*|*/.|.|*\\*) return 1;; esac
}

safe_path() {
    lexical_path "$1" || return 1
    remaining=$1
    parent=otp
    while :; do
        part=${remaining%%/*}
        parent=$parent/$part
        test ! -L "$parent" || return 1
        case "$remaining" in */*) remaining=${remaining#*/};; *) break;; esac
    done
}

parse_line() {
    hash=${1%%  *}
    path=${1#*  }
    test "$path" != "$1"
    test ${#hash} -eq 64
    case "$hash" in *[!0-9a-f]*) return 1;; esac
    test "$path" != "$receipt"
    lexical_path "$path"
}

valid_line() {
    parse_line "$1"
    safe_path "$path"
}

digest() {
    sha256sum "$1" | cut -d ' ' -f 1
}

# Only regular files beneath otp/ are accepted. Check headers and names before
# extracting, so neither links nor traversal can write outside the private stage.
tar tf "$archive" > "$stage/members"
sort "$stage/members" | uniq -d > "$stage/duplicate-members"
test ! -s "$stage/duplicate-members"
tar tvf "$archive" > "$stage/headers"
while IFS= read -r line || test -n "$line"; do
    case "$line" in -*) :;; *) exit 1;; esac
done < "$stage/headers"
while IFS= read -r member || test -n "$member"; do
    case "$member" in otp/*) path=${member#otp/};; *) exit 1;; esac
    if test "$path" != "$receipt"; then safe_path "$path"; fi
done < "$stage/members"
tar xf "$archive" -C "$stage"
test -f "$stage/otp/$receipt"
cut -c 67- "$stage/otp/$receipt" > "$stage/paths"
sort "$stage/paths" | uniq -d > "$stage/duplicates"
test ! -s "$stage/duplicates"
while IFS= read -r member || test -n "$member"; do
    test "$member" = "otp/$receipt" || grep -F -x "${member#otp/}" "$stage/paths" >/dev/null
done < "$stage/members"

# Check the complete new selection and every target path before the first write.
while IFS= read -r line || test -n "$line"; do
    valid_line "$line"
    test -f "$stage/otp/$path"
    test ! -L "$stage/otp/$path"
    test "$(digest "$stage/otp/$path")" = "$hash"
done < "$stage/otp/$receipt"
if test -f "otp/$receipt"; then
    while IFS= read -r line || test -n "$line"; do parse_line "$line"; done < "otp/$receipt"
fi

while IFS= read -r line || test -n "$line"; do
    valid_line "$line"
    destination=otp/$path
    if test -e "$destination"; then
        test -f "$destination"
        current=$(digest "$destination")
        test "$current" != "$hash" || continue
        # Preserve a changed prior runtime file too; ownership alone never
        # permits destroying bytes which differ from the published receipt.
        if ! test -f "otp/$receipt" || ! grep -F -x "$current  $path" "otp/$receipt" >/dev/null; then
            if test "$backup_created" = 0; then
                test ! -e "$backup" && test ! -L "$backup"
                mkdir "$backup"
                backup_created=1
            fi
            mkdir -p "$backup/$(dirname "$path")"
            cp -p "$destination" "$backup/$path"
        fi
    fi
    mkdir -p "$(dirname "$destination")"
    if test -e "$destination"; then chmod u+w "$destination"; fi
    cp -p "$stage/otp/$path" "$destination"
done < "$stage/otp/$receipt"

if test -f "otp/$receipt"; then
    while IFS= read -r line || test -n "$line"; do
        parse_line "$line"
        if ! grep -F -x "$line" "$stage/otp/$receipt" >/dev/null; then
            # A retained path with new bytes is a replacement, not obsolete.
            if grep -F -x "$path" "$stage/paths" >/dev/null; then
                continue
            fi
            # A changed kind or parent belongs to the running application now.
            # Preserve it without following links and drop obsolete ownership.
            if safe_path "$path" && test -f "otp/$path" && test "$(digest "otp/$path")" = "$hash"; then
                rm -f "otp/$path"
                parent=$(dirname "otp/$path")
                while test "$parent" != otp && rmdir "$parent" 2>/dev/null; do parent=$(dirname "$parent"); done
            fi
        fi
    done < "otp/$receipt"
fi
mv "$stage/otp/$receipt" "otp/$receipt"
