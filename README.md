# MAGOS
Tools for editing AGOS games (e.g. Simon the Sorcerer by AdventureSoft)

## Supported features
- Extract and edit files from GME archives
- Extract, decrypt and edit game texts
- Extract and edit voices
- Decompile and recompile game scripts

Currently supported games are:
- Simon the Sorcerer (Floppy)
- Simon the Sorcerer (CD)
- Simon the Sorcerer 2 (Floppy)
- Simon the Sorcerer 2 (CD)
- The Feeble Files

## Installation
The latest release can be grabbed from the [Releases](https://github.com/BLooperZ/magos/releases) page.

Just download and extract the archive.

## Usage

The main entrypoint of the program is CLI utility called `magos`

### Extract the game texts
This is the default action and will always happen[[*]](#rebuild-the-game).

point the program to the GME file
for example:
```
magos PATH/TO/SIMON.GME
```
This will create a file called `strings.txt` in working directory with all the game texts.

You can optionally change the name of the file by adding `-o <other name>` where `<other name>` is the desired name of the file.
for example:
```
magos PATH/TO/SIMON.GME -o messages.txt
```

Now let's see some more uses, feel free to combine them (add all modification in one command).

### Game is not detected correctly
The tool tries to infer which game it is operating on by the name of the files.

If file was renamed so the detection fail, or you just wish to force it to specific game, add `-g <game>` where `<game>` is identifier of the game.

Simon the Sorcerer -> simon

Simon the Sorcerer 2 -> simon2

The Feeble Files -> feeble

examples:
```
magos PATH/TO/SIMON.GME -g simon
```
```
magos PATH/TO/SIMON2.GME -g simon2
```

### Game version doesn't have GME files
Some versions do not have a GME archive (e.g. Simon 1 Floppy),
point it to the game directory instead and add `-m` flag:
```
magos PATH/TO/ -m
```
Please keep in mind that this usage might also require specifying the game[[*]](#game-is-not-detected-correctly).

### Extract GME archive
NOTE: This won't do anything if the game doesn't have GME archive[[*]](#game-version-doesnt-have-gme-files).

To create a directory containing the content of the GME file in separate files.

Add `-e <directory>` where `<directory>` is the desired name of the directory.
for example:
```
magos PATH/TO/SIMON.GME -e ext
```
will extract the content of the GME archive to a directory name `ext` inside current working directory.

### Decompile game scripts
You can view the game scripts and object by adding `-s <variant>` where `<variant>` indicates if the game is `floppy` or `talkie`.

When used on the Talkie edition it will also match each line of text with it's corresponding voice file[[*]](#extract-voice-files).
```
magos PATH/TO/SIMON.GME -s talkie
```
This will create 2 files in working directory
`scripts.txt` will contain the decompiled script
`objects.txt` will contain object information.

You can optionally change the name of the `scripts.txt` by adding `-d <other name>` where `<other name>` is the desired name of the file.
for example:
```
magos PATH/TO/SIMON.GME -s talkie -d decomp.txt
```

The decompiled script file can be used for recompiling the script when rebuilding[[*]](#rebuild-the-game).

### Extract voice files
To create a directory containing each voice sample in separate file.

add `-t <voice file>` where `<voice file>` is the path to the game soundbank file.
for example:
```
magos PATH/TO/SIMON.GME -t PATH/TO/SIMON.VOC
```
this will create a directory called `voices` in working directory.

Inside, you will find the extracted sound files.

### Decrypt strings
The multilingual versions of the games do not follow standard encodings closely.
For instance, Hebrew version of the game overrides the uppercase English letters.
Thus, for convenience, there is an option to map the text messages in game to the actual character glyph per language in standard encoding.

Use `-c LANG` flag to replace in-game glyphs with actual characters for reading writing.
where `LANG` can be either one of:
- `he` for Hebrew (Codepage 1255)
- `de` for German (Codepage 1252)
- `es` for Spanish (Codepage 1252)
- `fr` for French (Codepage 1252)
- `it` for Italian (Codepage 1252)
- `pl` for Polish (Codepage 1250)
- `ru` for Russian (Codepage 1251)

You may also leave out this option completely to save the texts as is (use same byte values as were used in game)

```
magos PATH/TO/SIMON.GME -c he
```

Additionaly, you may add `-u` flag to convert the text to UTF-8 encoding
```
magos PATH/TO/SIMON.GME -c he -u
```

### Rebuild the game
After editing the desired files, you can inject it back to the game.
just use whatever command you used to extract and add `-r`.

(Of course, you can remove some parts if you don't wish to edit them)

for example:
assuming extraction script was
```
magos SIMON2.GME -c he -e ext -s talkie -t SIMON2.VOC
```
game can be rebuilt using:
```
magos SIMON2.GME -c he -e ext -s talkie -t SIMON2.VOC -r
```
The parameters themselves are used for the reverse action.

e.g. the tool will now read from `strings.txt` to write game files.

The edited files will be created in current working directory regardless of where the actual files were.

This is to allow keeping the game intact in a subdirectory and copy changes manually.

If you wish the tool to always override the game files, just launch it from the game directory itself.

## Cool stuff to implement sometime
* Document how to modify game scripts
* Extract and edit game graphics (VGA files)
* Support more games

## Thanks
* AdventureSoft for Simon the Sorcerer games
* ScummVM and ScummVM Tools
* MojoTouch for the Anniversary Edition
* Hebrew Adventure Group
