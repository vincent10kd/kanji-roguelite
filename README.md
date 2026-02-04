# 漢字修行
A terminal-based Japanese vocabulary roguelike built with **Textual**.
Explore procedurally generated maps, fight enemies by typing correct readings,
and level up to unlock more difficult vocabulary.

## Requirements
- Python **3.10+**
- A terminal with Unicode support (most modern terminals are fine)

## Installation

```bash
git clone https://github.com/YOURNAME/kanji-roguelite.git
cd kanji-roguelite
pip install -r requirements.txt
```

## Dictionary data (required)

This game uses **JMdict** for readings and meanings.
It's in: 
data/jmdict.sqlite
```
JMdict is Â© the Electronic Dictionary Research and Development Group and is used
under the **Creative Commons Attribution-ShareAlike** license.

## Run

```bash
python main.py
```

## Controls
- **Arrow keys** â move
- **Type romaji** â answer during battles
- **Enter / Space** â continue after battle messages
- **Esc** â quit

## Notes
- `fugashi` / MeCab is optional but recommended for best readings.
- The game will fall back gracefully if some optional components are missing.

## License
Code is released under the **MIT License**.
