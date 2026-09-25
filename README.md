# Receipt-OCR-Algorithm
As part of my IBDP CS IA, this is a Python-based OCR application that can extract  data from scanned supplier receipts and outputs them in a structured spreadsheet. The aim is  primarily to reduce the need for repetitive manual entry, which will also reduce human errors.

SECTION 1: WHAT THIS PROGRAM DOES
=================================

This program lets you:
Load a scanned invoice/receipt image (JPG/JPEG/PNG).
Draw and adjust Areas of Interest (AOI) for: Supplier, Date, Item code, Item description, Quantity, Satuan (unit), Unit price, Discount, Amount, Total.
Preview the cropped regions before running OCR.
Run OCR (Optical Character Recognition) using Tesseract.
Review and manually edit all extracted data in a table.
Export the corrected data to Excel (.xlsx).

SECTION 2: SYSTEM REQUIREMENTS
==============================

Operating system: Windows 10/11
Python: 3.11.0
Download from:
https://www.python.org/downloads/release/python-3110/

!!! MAKE SURE TO ADD PYTHON 3.11.0 TO PATH DURING THE INSTALLATION PROCESS !!!

Tesseract OCR
https://github.com/tesseract-ocr/tesseract
On Windows, it is usually installed at:
C:\Program Files\Tesseract-OCR\tesseract.exe

Python packages (install via pip):
Command Prompt:
pip install pillow opencv-python numpy pytesseract openpyxl


SECTION 3: PROJECT FILES
========================

main.py (Main application)
config.json
Stores AOI box positions and Tesseract path.
If config.json does not exist, it will be created automatically the first time you run the program.
Clicking 'reload config.json' will bring all AOI boxes to its original position, as it's stored in the file
Clicking 'Save boxes' will update config.json to the current position of the boxes, as seen in the user interface


SECTION 4: HOW TO RUN THE PROGRAM
=================================

Open a terminal / command prompt in the project folder.
To do this, use the cd command. Example:
cd ~ … cd Downloads … cd receipt_ocr
Run: python main.py

The “Invoice OCR — Box Editor” window will appear.


SECTION 5: SUPPORTED IMAGE FORMATS
==================================

The program only allows the following file types when opening an image:
.jpg
.jpeg
.png
Other image formats (TIFF, BMP, etc.) are not accepted by the file dialog.


SECTION 6: BASIC WORKFLOW
=========================

STEP 1 – Open an invoice image
---

Click “Open Image”.
Select a .jpg, .jpeg, or .png file.
The image will appear in the centre of the window.
Green boxes (AOIs) will be drawn in approximate default positions.

Each box corresponds to a specific field.

STEP 2 – Adjust Areas of Interest (AOI)
---

Each box corresponds to a field: supplier, date, total, item, item_desc, quantity, satuan, unit_price, disc, amount

Header fields: supplier, date, total

Table fields: item, item_desc, quantity, satuan, unit_price, disc, amount

To adjust a box:
Move: Click inside the box and drag to move it.
Resize: Drag from a corner (top-left, top-right, bottom-left, bottom-right).

Tip:
Align each box tightly around the text you want Tesseract to read.


STEP 3 – Save AOI configuration (optional but recommended)
---

Once AOIs are correctly aligned for a given invoice format:
1. Click “Save boxes”.
2. The box positions are saved to config.json as relative coordinates,
   so they will still work for future runs of the program.

Next time you open an invoice with the same layout,
you do not need to redraw the boxes.


STEP 4 – Preview crops
---

To check if boxes are correctly placed:

1. Click “Preview crops”.
2. A new window will show, for each field:
The original crop.
The pre-processed (black and white) version that OCR will see.

If something looks misaligned or cut off, close the preview and
adjust the boxes, then preview again.


STEP 5 – Run OCR
---

1. Click “Run OCR”.
2. The program will preprocess each crop, run Tesseract OCR,
   and parse the table.
3. An “Edit OCR Data & Export” window will open automatically.

If Tesseract is not installed or misconfigured,
an error message will appear instead.


STEP 6 – Review and edit extracted data
---

In the “Edit OCR Data & Export” window:

At the top: Supplier, Date, Total are shown in text fields.
   You can edit them manually.

In the table grid: columns
   ITEM, DESCRIPTION, QTY, SATUAN, UNIT_PRICE, DISC, AMOUNT.
   Each cell is editable.

All edits here will be saved when you export.

If “Run OCR” finishes without opening the edit window, it is likely that not all required columns
(item, item_desc, quantity, satuan, unit_price, disc, amount) could be read.

Fix:
Adjust the AOI boxes and try again.
Make sure the table area is fully inside the
   item + item_desc + numeric column boxes.


STEP 7 – Export to Excel
---

After reviewing and editing data, click “Export to Excel (.xlsx)”.
Choose a file name and location (for example: invoice_data.xlsx).

You can then open the .xlsx file in Excel, Google Sheets,
or other spreadsheet software.


SECTION 7: TESSERACT CONFIGURATION
==================================

The program tries to use Tesseract in this order:

If config.json has a non-empty "tesseract_cmd" value, it uses that exact path.
Otherwise, it expects "tesseract" to be available in the system PATH.

Setting the Tesseract path manually:
Find where Tesseract is installed, for example: C:\Program Files\Tesseract-OCR\tesseract.exe
Open config.json.
Set the "tesseract_cmd" value to that full path, for example: "tesseract_cmd": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
Save config.json.

If the path is wrong or Tesseract is not installed,
the program will show an error message when you click “Run OCR”.
