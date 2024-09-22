# MAGOS
Tools for editing AGOS games (e.g. Simon the Sorcerer by AdventureSoft)

## Supported Features
- Extract and edit files from GME archives
- Extract, decrypt, and edit game texts
- Extract and edit voices
- Decompile and recompile game scripts

### Currently Supported Games
- Elvira: Mistress of the Dark
- Elvira II: The Jaws of Cerberus
- Waxworks
- Simon the Sorcerer
- Simon the Sorcerer II: The Lion, the Wizard and the Wardrobe
- The Feeble Files
- Simon the Sorcerer's Puzzle Pack

## Installation
The latest release can be grabbed from the [Releases](https://github.com/BLooperZ/magos/releases) page.

Just download and extract the archive.

## Usage

The main entry point of the program is a CLI utility called `magos`.

### Extract Game Texts
This is the default action and will always happen.

Point the program to the game directory, for example:
```
magos PATH/TO/GAME
```
This will create a file called `strings.txt` in the working directory with all the game texts.

You can optionally change the name of the file by adding `-o <other name>`, where `<other name>` is the desired name of the file. For example:
```
magos PATH/TO/GAME -o messages.txt
```

### Game Not Detected Correctly
When using the tool on a directory, it will attempt to detect the game automatically based on the names of the files in the given directory.

If you prefer, or if the tool fails to detect the game, you can force it to recognize a specific game by adding `-g <game>`, where `<game>` is the identifier of the game.

Available Identifiers for supported games:
- Elvira: Mistress of the Dark - use `elvira1`
- Elvira II: The Jaws of Cerberus - use `elvira2`
- Waxworks
    - Retail version - use `waxworks`
    - Demo version - use `waxworks-demo`
- Simon the Sorcerer
    - Floppy version - use `simon1`
    - Demo version - use `simon1-demo`
    - Talkie versions (CD and 25th Anniversary) - use `simon1-talkie`
- Simon the Sorcerer II: The Lion, the Wizard and the Wardrobe
    - Floppy version - use `simon2`
    - Talkie versions (Demo, CD, and 25th Anniversary) - use `simon2-talkie`
- The Feeble Files - use `feeble`
- Simon the Sorcerer's Puzzle Pack
    - Swampy Adventures - use `swampy`
    - NoPatience - use `puzzle`
    - Jumble - use `jumble`
    - Demon in my Pocket - use `dimp`

Examples:
```
magos PATH/TO/GAME -g simon1
```
```
magos PATH/TO/GAME -g simon2-talkie
```

### Extract GME Archive
To create a directory containing the content of the GME file in separate files, add `-e <directory>`, where `<directory>` is the desired name of the directory. For example:
```
magos PATH/TO/GAME -e ext
```
This will extract the content of the GME archive to a directory named `ext` inside the current working directory.

### Decompile Game Scripts
To view the game scripts and objects, add the `-s` flag. For example:
```
magos PATH/TO/GAME -s
```
This will create two files in the working directory:
- `scripts.txt` will contain the decompiled script
- `objects.txt` will contain object information

You can optionally change the name of the `scripts.txt` file by adding `<name>` after the flag, where `<name>` is the desired name of the file. For example:
```
magos PATH/TO/GAME -s decomp.txt
```

### Extract Voice Files
To create a directory containing each voice sample in a separate file, add `-t <voice file>`, where `<voice file>` is the path to the game soundbank file. For example:
```
magos PATH/TO/GAME -t SIMON.VOC
```
This will create a directory called `voices` in the working directory with the extracted sound files.

### Decrypt Strings
To map the text messages in the game to the actual character glyph per language in standard encoding, use the `-c LANG` flag, where `LANG` can be one of:
- `he` for Hebrew (Codepage 1255)
- `de` for German (Codepage 1252)
- `es` for Spanish (Codepage 1252)
- `fr` for French (Codepage 1252)
- `it` for Italian (Codepage 1252)
- `pl` for Polish (Codepage 1250)
- `ru` for Russian (Codepage 1251)

For example:
```
magos PATH/TO/GAME -c he
```

Additionally, you may add the `-u` flag to convert the text to UTF-8 encoding:
```
magos PATH/TO/GAME -c he -u
```

Leave out this option completely to save the texts as is, with the same encoding used in the game.

### Rebuild the Game
After editing the desired files, you can inject them back into the game by adding the `-r` flag to your extraction command. For example:

Assuming the extraction command was:
```
magos PATH/TO/GAME -c he -e ext -s -t SIMON2.VOC
```

The game can be rebuilt using:
```
magos PATH/TO/GAME -c he -e ext -s -t SIMON2.VOC -r
```
This will read from `strings.txt` and write the game files. The edited files will be created in the current working directory.

## Cool Stuff to Implement Sometime
* Document how to modify game scripts
* Extract and edit game graphics (VGA files)

## Thanks
* AdventureSoft for Simon the Sorcerer games
* ScummVM and ScummVM Tools
* MojoTouch for the Anniversary Edition
* Hebrew Adventure Group
