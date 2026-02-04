# 漢字修行
A terminal-based Japanese vocabulary roguelike built with **Textual**.
Explore procedurally generated maps, fight enemies by typing correct readings,
and level up to unlock more difficult vocabulary.

<img width="397" height="420" alt="image" src="https://github.com/user-attachments/assets/5e3b512a-84f4-4d3c-bc5b-47d68a4ff567" />
A procedurally generated map, with @ indicating the player position, E enemies, and ! HP potions.
<br><br>
<img width="436" height="188" alt="image" src="https://github.com/user-attachments/assets/908ed02b-1e52-4712-afd6-18e542642b73" />
Battle view


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
- **Arrow keys** move
- **Type romaji** answer during battles
- **Enter / Space**  continue after battle messages
- **Esc**  quit

## Notes
- `fugashi` / MeCab is optional but recommended for best readings.
- The game will fall back gracefully if some optional components are missing.

## License
Code is released under the **MIT License**.
