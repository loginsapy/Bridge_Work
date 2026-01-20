# 1) Asegúrate de estar en el repo correcto y actualiza remotos
git remote -v
git fetch --all --tags --prune

# 2) Intentar crear una rama directamente desde el commit (si el commit es accesible localmente tras el fetch)
git checkout -b restore/73ab2e7 73ab2e72bdd7b35e7c3f2c11d506c471c4fae310

# 3) Si falla porque el SHA no existe localmente, descarga el patch desde GitHub y aplícalo
# (repositorio: https://github.com/barons23/Bridgework2)
curl -L -H "Accept: application/vnd.github.v3.patch" \
  https://github.com/barons23/Bridgework2/commit/73ab2e72bdd7b35e7c3f2c11d506c471c4fae310 \
  -o /tmp/73ab2e7.patch

# aplicar como commit preservando autor/fecha
git checkout -b restore/73ab2e7-temp
git am < /tmp/73ab2e7.patch

# Alternativa si git am falla: aplicar como cambios y commitear manualmente
# git apply --check /tmp/73ab2e7.patch && git apply /tmp/73ab2e7.patch
# git add -A && git commit -m "Restore commit 73ab2e7 from GitHub (manual apply)"

# 4) Extraer solo un archivo desde el commit (si prefieres recuperar archivos puntuales)
# git show <sha>:path/to/file > path/to/file

# 5) Empujar la rama restaurada al remoto
git push origin HEAD:refs/heads/restore/73ab2e7

# 6) Si necesitas inspeccionar el commit antes de aplicar:
git show 73ab2e72bdd7b35e7c3f2c11d506c471c4fae310
# o abrir en navegador:
# https://github.com/barons23/Bridgework2/commit/73ab2e72bdd7b35e7c3f2c11d506c471c4fae310
