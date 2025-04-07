# MAGOS

Tools for editing AGOS games (e.g., Simon the Sorcerer by AdventureSoft).

## Table of Contents

1. [Introduction](#introduction)
2. [Features](#features)
3. [Supported Games](#supported-games)
4. [Installation](#installation)
5. [Usage](#usage)
    1. [Interactive Mode](#interactive-mode)
    2. [Non-Interactive Mode](#non-interactive-mode)
6. [Getting Help](#getting-help)
7. [Contributions](#contributions)
8. [Open Items](#open-items)
9. [Thanks](#thanks)
10. [Development](#development)
11. [License](#license)

## Introduction

MAGOS is a tool for exploring, modifying, and enhancing AGOS games. Whether you want to translate, mod, or learn how these games work, MAGOS makes it easy to access and edit game resources.

## Features

- Unpack and Repack GME Archives
- Decrypt and Edit Game Texts
- Extract and Modify Voice Files
- Decompile and Recompile Game Scripts

## Supported Games

MAGOS supports the following AGOS games:

- **Elvira: Mistress of the Dark** (`elvira1`)
- **Elvira II: The Jaws of Cerberus** (`elvira2`)
- **Waxworks**
    - Retail version (`waxworks`)
    - Demo version (`waxworks-demo`)
- **Simon the Sorcerer**
    - Floppy version (`simon1`)
    - Demo version (`simon1-demo`)
    - Talkie versions (CD and 25th Anniversary) (`simon1-talkie`)
- **Simon the Sorcerer II: The Lion, the Wizard and the Wardrobe**
    - Floppy version (`simon2`)
    - Talkie versions (Demo, CD, and 25th Anniversary) (`simon2-talkie`)
- **The Feeble Files** (`feeble`)
- **Simon the Sorcerer's Puzzle Pack**
    - Swampy Adventures (`swampy`)
    - NoPatience (`puzzle`)
    - Jumble (`jumble`)
    - Demon in My Pocket (`dimp`)

## Installation

1. Download the latest release for your OS from the [Releases](https://github.com/BLooperZ/magos/releases) page.
2. Extract the downloaded archive to a folder of your choice.
3. Run the tool directly from the extracted folder.

The program is a single executable file and does not require any additional dependencies.

## Usage

MAGOS can be used in two modes: **Interactive Mode** (recommended for most users) and **Non-Interactive Mode** (for advanced users). Both modes allow you to extract and work with various game resources, including texts, scripts, voices, and archives.

### Interactive Mode

Interactive mode provides a simple, menu-driven interface that you can navigate using your keyboard or mouse. It is the default mode when the tool is run without any arguments (or with only the game directory path).

#### How to Use Interactive Mode

1. **Start the Tool**:
   Run the tool without any arguments:
   ```sh
   magos
   ```
   Or specify the game directory:
   ```sh
   magos PATH/TO/GAME
   ```

2. **Select a Directory**:
   Use the directory selection option to choose the game directory. If needed, switch to a different directory to work on another game.

3. **Game Selection**:
   The tool will attempt to detect the game automatically based on the directory contents and select it. If detection fails, you can manually select the game from a list.

4. **Configure Features**:
   Features are dynamically available based on the selected game. Use the interactive controls to toggle features like extracting scripts, archives, and voices, or to configure output file names and encoding settings.

5. **Extract Resources**:
   Use the "Extract" button to extract resources such as texts, voices, or scripts. The resources will be saved in the working directory, i.e., the folder you started the program from.

6. **Modify Extracted Files**:
   Make any desired modifications to the extracted files using external tools or editors. MAGOS itself does not provide editing capabilities for the extracted files.

7. **Rebuild the Game**:
   After making changes to the extracted files, use the "Rebuild" button to inject your modifications back into the game. If the rebuild process encounters any errors, they will be displayed in the output panel.

8. **Exit**:
   When you're done, select "Exit" or press `Ctrl+D` to close the tool.

Interactive mode automatically saves your settings in a `magos.toml` file in the selected directory. These settings are restored when you select the same directory again.

### Non-Interactive Mode

Non-interactive mode is designed for advanced users who prefer working with command-line tools or need to automate tasks. It allows you to specify actions and options directly via command-line arguments, providing flexibility for various use cases.

#### Default Behavior
By default, running `magos PATH/TO/GAME` launches the tool in **interactive mode**. To run it in non-interactive mode, use the `-n` flag:
```sh
magos PATH/TO/GAME -n
```

The tool always extracts all game texts and saves them to a file in the working directory. By default, the file is named `strings.txt`. You can customize the name or perform additional actions using the options below.

#### Available Options

1. **Change Output File Name**:
   Use the `-o` flag to specify a custom name for the extracted texts file:
   ```sh
   magos PATH/TO/GAME -n -o messages.txt
   ```

2. **Specify the Game**:
   If the game is not detected correctly, you can manually specify the game using the `-g` flag:
   ```sh
   magos PATH/TO/GAME -n -g simon1
   ```
   Refer to the [Supported Games](#supported-games) section for the list of game identifiers.

3. **Extract GME Archive**:
   To extract the contents of a GME archive into a directory, use the `-e` flag:
   ```sh
   magos PATH/TO/GAME -n -e ext
   ```
   This will create a directory named `ext` in the working directory containing the extracted files.

4. **Decompile Game Scripts**:
   Use the `-s` flag to decompile game scripts and objects:
   ```sh
   magos PATH/TO/GAME -n -s
   ```
   This will create two files in the working directory:
   - `scripts.txt` for the decompiled script
   - `objects.txt` for object information

   To specify a custom name for the `scripts.txt` file, add the desired name after the `-s` flag:
   ```sh
   magos PATH/TO/GAME -n -s decomp.txt
   ```

   Similarly, to specify a custom name for the object information file, use the `-i` flag:
   ```sh
   magos PATH/TO/GAME -n -s decomp.txt -i items.txt
   ```

5. **Extract Voice Files**:
   Use the `-t` flag to extract voice samples from the game's soundbank:
   ```sh
   magos PATH/TO/GAME -n -t SIMON.VOC
   ```
   This will create a directory named `voices` in the working directory containing the extracted sound files.

6. **Decrypt Strings**:
   Use the `-c` flag to decrypt game texts for a specific language:
   ```sh
   magos PATH/TO/GAME -n -c he
   ```
   Supported languages include:
   - `he` for Hebrew
   - `de` for German
   - `es` for Spanish
   - `fr` for French
   - `it` for Italian
   - `pl` for Polish
   - `ru` for Russian

   You can also convert the decrypted texts to UTF-8 encoding using the `-u` flag:
   ```sh
   magos PATH/TO/GAME -n -c he -u
   ```

7. **Rebuild the Game**:
   The same command used to extract resources can also be used to rebuild them by adding the `-r` flag. For example:

   If you have extracted resources with the following command:
   ```sh
   magos PATH/TO/GAME -c he -e ext -s -t SIMON.VOC
   ```

   You can rebuild the game with:
   ```sh
   magos PATH/TO/GAME -c he -e ext -s -t SIMON.VOC -r
   ```

## Getting Help

If you have questions or encounter issues, you can:

- Check the [issues section](https://github.com/BLooperZ/magos/issues) on GitHub.
- Look for community resources or discussions.

## Contributions

Contributions are welcome! Feel free to submit issues, fork the repository, and send pull requests.

## Open Items

The following are potential areas for future exploration and improvement:
- **Document the script language**: Provide detailed documentation on the commands and structure of the script language to assist with editing and recompiling game scripts.
- **Extract and edit game graphics (VGA files)**: Add support for extracting and modifying graphical assets.

## Thanks

Special thanks to:

- **AdventureSoft** for making these games.
- **ScummVM and ScummVM Tools** for their invaluable work, which made this project possible.
- **MojoTouch** for the Anniversary Edition.
- **Hebrew Adventure Group** for inspiring this project.
- **Alan Cox** for releasing AberMUD as free software.

## Development

To develop or contribute to this project, you can clone the repository and set it up using Python >= 3.12 and [Poetry](https://python-poetry.org/) (a tool for dependency management and packaging in Python).

### Running Development Version

1. **Clone the Repository**:
   ```sh
   git clone https://github.com/adventurebrew/magos.git
   ```

2. **Navigate to the Project Directory**:
   ```sh
   cd magos
   ```

3. **Ensure you have Python >= 3.12 installed**:
   You can check your Python version by running:
   ```sh
   python --version
   ```

4. **Install Dependencies**:
   Install the required dependencies using Poetry:
   ```sh
   poetry install
   ```

5. **Activate Poetry Shell**:
   Activate the Poetry virtual environment:
   ```sh
   poetry shell
   ```

Now you have the `magos` program available to execute from your shell, with the ability to modify the program locally.

## License

This project is licensed under the GPL-3.0 License. See the `LICENSE` file for more details.

**Disclaimer:** This is a fan-made project and is not affiliated with or endorsed by the copyright holders of the original AGOS games. All trademarks are the property of their respective owners.
