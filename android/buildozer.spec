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

# python-for-android берётся выпуском, а не master. master строит
# hostpython 3.14, и вложенный в неё pip падает на импорте
# BuildDependencyInstallError — сборка умирает через восемнадцать
# минут, дойдя до компиляции Kivy. v2026.05.09 вышел за два дня до
# buildozer 1.6.0: это пара, которую собирали вместе.
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
warn_on_root = 0
