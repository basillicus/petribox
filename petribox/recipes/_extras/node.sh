# description: Node.js (through mise; LTS unless pinned, e.g. node@24.22.1)
# needs: mise
as_user "mise use -g node@${VERSION:-lts}"
