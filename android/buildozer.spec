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

[buildozer]
log_level = 2
warn_on_root = 0
