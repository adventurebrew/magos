# agos-tools
Scripts for splitting and merging Simon the Sorcerer voices and data files

## usage

split master voc file to individual voice files (assuming SIMON.VOC is put in same directory)
```
python split-voc.py SIMON.VOC
```

build master voc file from individual files
```
python split-voc.py SIMON-NEW.VOC
```

extract text files in editable format from GME file
```
python split-gme.py [--decrypt he] SIMON.GME
```

build GME file with edited texts
```
python merge-gme.py [--decrypt he] SIMON-NEW.GME
```

## todo
* make script accept cli parameters
* add support for Simon the Sorcerer 2 and another versions of Simon the Sorcerer 1
* find out how to edit VGA files
* find out how to know types of extracted files

## thanks
* AdventureSoft for Simon the Sorcerer games
* ScummVM and ScummVM Tools
