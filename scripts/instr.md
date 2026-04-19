Please create a virtual environment inside the scripts directory.
For convenience and to automate build, we can all name it `.venv`

Command:
```shell
python3 -m venv .venv
```

To install the required packages, the build system will first activate this virtual environment, and then run the install command for the requirements.
I have added the above to `.gitignore` file, so it won't get committed to the repo, but creating it is highly advised, (until it is automated).
The directory structure should be something like this:
```shell
├── scripts/
│   ├── pipeline/
│   │   └── All python files for pipelines
│   ├── requirements.txt
│   ├── instr.md
│   └── .venv/
```
