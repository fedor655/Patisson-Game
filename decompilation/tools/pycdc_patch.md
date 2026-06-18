# Патчи к pycdc (Decompyle++) под Python 3.12

Базовый pycdc (`github.com/zrax/pycdc`) на этом байткоде падал/игнорировал ряд
опкодов 3.12. Ниже — что добавлено в `ASTree.cpp` (декомпилятор → AST). Все
правки точечные, не ломают рабочие функции (проверено верификатором).

> Пути в `tools/*.py` машинно-зависимые (хардкод под конкретную машину) — это
> рабочие скрипты эксперимента, для воспроизведения поправьте пути вверху файлов.

## 1. `CALL_INTRINSIC_1` → `INTRINSIC_IMPORT_STAR`
В 3.12 `from x import *` компилируется в `IMPORT_NAME` + `CALL_INTRINSIC_1` с
операндом 2. pycdc знал только старый опкод `IMPORT_STAR`. Добавлен `case` для
`CALL_INTRINSIC_1_A`: при операнде 2 — то же, что `IMPORT_STAR`; прочие
intrinsic-1 (например `INTRINSIC_STOPITERATION_ERROR`) — no-op, чтобы не рвать кадр.

## 2. `POP_JUMP_IF_NONE` / `POP_JUMP_IF_NOT_NONE`
Новые в 3.12 условные переходы «TOS is (not) None». Добавлены в общий обработчик
переходов: синтезируется сравнение `value is None` / `value is not None` (с
инверсией смысла — `POP_JUMP_IF_NONE` уходит от тела `is not None`, поэтому
ведёт себя как обычный jump-if-false), помечаются как «pop condition before jump».

## 3. `MAKE_CELL`, `COPY_FREE_VARS`, `RETURN_GENERATOR`
Подготовка кадра для замыканий/генераторов. `MAKE_CELL`/`COPY_FREE_VARS` —
no-op (не влияют на исходник). `RETURN_GENERATOR` (старт генератора) кладёт
заглушку на стек, т.к. следом идёт `POP_TOP` — чтобы стек остался сбалансирован.

## 4. `LOAD_FAST_CHECK`
То же значение, что `LOAD_FAST` (для возможно-несвязанных локальных). Трактуется
идентично.

## Что НЕ патчилось (обходилось иначе)
- **Инлайн list/dict/set-comprehension** (`LOAD_FAST_AND_CLEAR`) — корректная
  поддержка в pycdc нетривиальна и нестабильна (попытки приводили к падению).
  Единственный такой блок в модуле вырезан хирургией `.pyc` (`surgery.py`),
  comprehension вписан вручную.
- **Инверсии булевых условий, `obj.attr += …`, генераторные выражения,
  `with`-блоки, дефолт-аргументы** — это не «неизвестные опкоды», а ошибки
  реконструкции pycdc. Исправлены вручную по дизассемблировке и подтверждены
  верификатором (сверка байткода с учётом направления переходов).

## Diff (суть)
В `ASTree.cpp`, в основном `switch(opcode)`:
- добавлен `case Pyc::CALL_INTRINSIC_1_A` (import-star + no-op);
- в блок условных переходов добавлены `POP_JUMP_IF_NONE_A`/`_NOT_NONE_A`
  (+ instrumented-варианты) с синтезом сравнения с `None`;
- добавлены `case`-ы `MAKE_CELL_A`/`COPY_FREE_VARS_A` (no-op),
  `RETURN_GENERATOR` (push None), `LOAD_FAST_CHECK_A` (как `LOAD_FAST`).
