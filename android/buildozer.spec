[app]

# Что ставится на телефон: тонкий клиент к общей ферме. Сама игра сюда не
# едет — она осталась на сервере, а телефон рисует вид сверху и передаёт
# касания. Поэтому в требованиях только Kivy: ни Panda3D, ни numpy.
title = Патиссон гейм
package.name = patisson
package.domain = io.github.fedor655

source.dir = .
source.include_exts = py,png,ico,txt
version = 2.0

requirements = python3,kivy==2.3.1

icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/icon.png
orientation = portrait
fullscreen = 0

# Единственное, что нужно приложению от телефона, — выйти в сеть.
android.permissions = android.permission.INTERNET

android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# Связка 2024 года. Дело было не в master: v2026.05.09 строит ту же
# hostpython 3.14, у которой ломается собственный pip —
# «cannot import name BuildDependencyInstallError» после
# восемнадцати минут работы. Выпуск 2024.01.21 строит Python 3.11 и
# обкатан годами; NDK к нему прикреплён свой, иначе буилдозер
# возьмёт свежий, с которым этот p4a не знаком.
p4a.branch = v2024.01.21
android.ndk = 25b

[buildozer]
log_level = 2
warn_on_root = 0
