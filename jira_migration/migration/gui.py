#!/usr/bin/env python
# Coding = UTF-8

"""
	This module will contain graphical user interface functionality.
"""

# Imports - Built-in


# Functions
from importlib import util
if (util.find_spec('tkinter')):
	import tkinter
	from tkinter.filedialog import askdirectory
	from tkinter.filedialog import askopenfilename as file_dialog
import sys
from types import SimpleNamespace


def get_filename_gui(window_title: str, search_filter: list) -> str:
	"""
	Display a file dialog and ask the user the select their desired file.

	Args:
		window_title(str): Title for the file dialog window.
		search_filter(list): list of lists - [[display name, extension],[...]]
			to filter for (e.g.[['CSV files','*.csv'], ['Excel files','*.xls *.xlsx']])

	Returns:
		(str): Absolute path and filename.
	"""

	filename = ''
	if 'tkinter' in sys.modules:
		root = tkinter.Tk()
		root.attributes('-topmost', True)
		root.withdraw()
		filename = file_dialog(parent=root, title=window_title, 
			filetypes=search_filter)
		root.destroy()
	return filename


def get_directory_gui(window_title: str) -> str:
	"""
	Display a file dialog and ask the user the select a directory.

	Args:
		window_title(str): Title for the file dialog window.

	Returns:
		(str): Absolute path.
	"""

	directory = ''
	if 'tkinter' in sys.modules:
		root = tkinter.Tk()
		root.attributes('-topmost', True)
		root.withdraw()
		directory = askdirectory(parent=root, title=window_title)
		root.destroy()
	return directory


def select_server(namespace: SimpleNamespace):
	"""
	Present GUI for server selection.
	"""

	pass


def get_project_key() -> str:
	"""
	Present GUI for project key input.
	"""

	pass
