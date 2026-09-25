    # main.py
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import json
import os

# image processing libs
import cv2
import numpy as np

CONFIG_PATH = "config.json"

# fields that are mainly numbers
NUMERIC_FIELDS = {"total", "quantity", "unit_price", "disc", "amount"}


# ----------------- config helpers -----------------
def load_config(path=CONFIG_PATH):
    """
    Load config.json.
    Boxes are stored as RELATIVE fractions of width/height: [x_frac, y_frac, w_frac, h_frac].
    This makes AOI (Area of Interest) definitions resolution-independent,
    so the same config works on different scans of the same invoice layout.
    """
    if not os.path.exists(path):
        # If no config file exists yet, create one with default AOIs. Supports success criterion (SC) 3 and 4
        cfg = {
            "boxes": {
                # Header info
                "supplier":   [0.23, 0.06, 0.42, 0.09],
                "date":       [0.70, 0.19, 0.26, 0.06],

                # Table columns
                "item":       [0.05, 0.40, 0.18, 0.35],  # SKU/Invoice code, etc.
                "item_desc":  [0.24, 0.40, 0.32, 0.35],  # description text
                "quantity":   [0.58, 0.40, 0.06, 0.35],  # Qty
                "satuan":     [0.65, 0.40, 0.07, 0.35],  # BTL, etc.
                "unit_price": [0.73, 0.40, 0.08, 0.35],  # Unit Price
                "disc":       [0.82, 0.40, 0.06, 0.35],  # Discount %
                "amount":     [0.89, 0.40, 0.09, 0.35],  # Amount per line

                # Grand total at the bottom-right
                "total":      [0.73, 0.83, 0.22, 0.08],
            },
            # set this if Tesseract is not on PATH
            "tesseract_cmd": "",
            # flag that boxes are stored as relative fractions
            "base_image_size": [1000, 1000],
        }
        with open(path, "w", encoding="utf-8") as f:
            # Save the default config
            json.dump(cfg, f, indent=2)
        return cfg

    # If config exists already, just load the JSON
    with open(path, "r", encoding="utf-8") as f:
        # Load existing config
        return json.load(f)


def save_config(cfg, path=CONFIG_PATH):
    # Save the current configuration back to config.json after user adjusts AOI boxes
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ----------------- main app -----------------
class ReceiptApp:
    def __init__(self, root):
        self.root = root
        root.title("Invoice OCR — Box Editor")
        self.cfg = load_config()
        self.img = None           # PIL image (original)
        self.tkimg = None         # PhotoImage for canvas
        self.scale = 1.0
        self.offset = (0, 0)

        # boxes in ABSOLUTE pixel coords for current image
        self.box_objects = {}

        # drag / resize state
        self.selected_box = None
        self.drag_mode = None     # "move", "resize_tl", "resize_tr", "resize_bl", "resize_br"
        self.drag_start = (0, 0)
        self.box_start = (0, 0, 0, 0)

        # last OCR table (for edit/export)
        self.last_table = None
        self.meta_entries = {}
        self.table_entries = []
        self.edit_win = None

        # UI toolbar
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=6)

        tk.Button(toolbar, text="Open Image", command=self.open_image).pack(side="left")
        tk.Button(toolbar, text="Reload config.json",
                  command=self.reload_config).pack(side="left", padx=(6, 0))
        tk.Button(toolbar, text="Save boxes",
                  command=self.save_boxes).pack(side="left", padx=(6, 0))
        tk.Button(toolbar, text="Preview crops",
                  command=self.preview_crops).pack(side="left", padx=(6, 0))
        tk.Button(toolbar, text="Run OCR",
                  command=self.run_ocr).pack(side="left", padx=(6, 0))

        # canvas
        self.canvas = tk.Canvas(root, bg="#333", width=900, height=700)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)

        # status bar
        self.status = tk.Label(root, text="No image loaded", anchor="w")
        self.status.pack(fill="x")

        # bind events
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        root.bind("<Configure>", self.on_resize)

    # ---------- box helpers (relative <=> absolute) ----------
    def upd_boxes(self):
        """
        Rebuild self.box_objects from config for the current image size.
        
        The config stores boxes as RELATIVE fractions (0–1),
        but the drawing/dragging logic works in absolute pixels.
        This method performs the conversion:
        (rx, ry, rw, rh)  ->  (x, y, w, h) in pixels
        based on the current image resolution.
        """
        self.box_objects = {} # name -> [x, y, w, h] in absolute pixels
        if not self.img:
            return

        boxes_cfg = self.cfg.get("boxes", {})
        img_w, img_h = self.img.size # current image size
        base_size = self.cfg.get("base_image_size", None) # [w, h] or None

        if base_size is not None:
            # boxes are stored as relative fractions (0–1)
            for name, vals in boxes_cfg.items():
                if len(vals) != 4:
                    continue
                # convert relative to absolute pixels
                rx, ry, rw, rh = vals
                x = rx * img_w
                y = ry * img_h
                w = rw * img_w
                h = rh * img_h
                self.box_objects[name] = [x, y, w, h]
        else:
            # legacy config: treat as absolute pixels (no auto-resize)
            for name, vals in boxes_cfg.items():
                if len(vals) != 4:
                    continue
                self.box_objects[name] = list(vals)

    def save_boxes(self):

        """
        Save current pixel boxes as relative fractions in config.json.
        This is the inverse transformation of upd_boxes():
        (x, y, w, h) in pixels  ->  (rx, ry, rw, rh) in 0–1 fractions.
        """
        if not self.img:
            # show warning if no image is loaded
            messagebox.showwarning(
                "Warning", "Load an image first before saving boxes." 
            )
            return

        img_w, img_h = self.img.size
        rel_boxes = {}
        for name, (x, y, w, h) in self.box_objects.items():
            # convert absolute pixels to relative fractions
            rel_boxes[name] = [x / img_w, y / img_h, w / img_w, h / img_h]

        # Overwrite config with updated relative AOIs.
        self.cfg["boxes"] = rel_boxes
        # Store the reference image size as a flag that the config uses relative coords
        self.cfg["base_image_size"] = [img_w, img_h]
        save_config(self.cfg)
        messagebox.showinfo("Saved", "Boxes saved to config.json!")

    def reload_config(self):
        self.cfg = load_config()
        self.upd_boxes()
        self.redraw()
        messagebox.showinfo("Reloaded", "config.json reloaded.")

    # ---------- image load ----------
    def open_image(self):
        path = filedialog.askopenfilename(
            title="Open invoice image",
            filetypes=[
                ("JPEG and PNG images", "*.jpg;*.jpeg;*.png"),
            ],
        )
        
        if not path:
            return
        try:
            pil = Image.open(path).convert("RGB")
            pil = ImageOps.exif_transpose(pil)
            self.img = pil
            self.status.config(
                text=f"Loaded: {os.path.basename(path)}  —  {pil.size[0]}x{pil.size[1]}"
            )
            # recompute absolute box positions for this resolution
            self.upd_boxes()
            self.redraw()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open image:\n{e}")

    # ---------- drawing ----------
    def on_resize(self, event):
        if self.img:
            self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        if not self.img:
            return

        c_w = self.canvas.winfo_width() or 900
        c_h = self.canvas.winfo_height() or 700
        img_w, img_h = self.img.size

        self.scale = min(c_w / img_w, c_h / img_h, 1.0)
        new_w = int(img_w * self.scale)
        new_h = int(img_h * self.scale)

        resized = self.img.resize((new_w, new_h), Image.LANCZOS)
        self.tkimg = ImageTk.PhotoImage(resized)

        offset_x = (c_w - new_w) // 2
        offset_y = (c_h - new_h) // 2
        self.offset = (offset_x, offset_y)

        self.canvas.create_image(offset_x, offset_y, image=self.tkimg, anchor="nw")

        # draw boxes
        for name, (x, y, w, h) in self.box_objects.items():
            sx = offset_x + x * self.scale
            sy = offset_y + y * self.scale
            ex = sx + w * self.scale
            ey = sy + h * self.scale
            outline = "cyan" if name == self.selected_box else "lime"
            self.canvas.create_rectangle(sx, sy, ex, ey, outline=outline, width=2)
            self.canvas.create_text(
                sx + 6, sy + 6, text=name, anchor="nw", fill=outline
            )

    # ---------- hit test ----------
    def find_box_at(self, px, py):
        """
        Determine which AOI (if any) has been clicked and whether the user
        grabbed a corner (resize) or the inside (move).
        """
        for name, (x, y, w, h) in self.box_objects.items():
            # Convert to scaled coords
            sx = self.offset[0] + x * self.scale
            sy = self.offset[1] + y * self.scale
            ex = sx + w * self.scale 
            ey = sy + h * self.scale
            cs = 12
            # Corners
            if abs(px - sx) < cs and abs(py - sy) < cs:
                return name, "resize_tl"
            if abs(px - ex) < cs and abs(py - sy) < cs:
                return name, "resize_tr"
            if abs(px - sx) < cs and abs(py - ey) < cs:
                return name, "resize_bl"
            if abs(px - ex) < cs and abs(py - ey) < cs:
                return name, "resize_br"
            # Otherwise, if the click is inside the box, goes to move mode
            if sx < px < ex and sy < py < ey:
                return name, "move"
        return None, None #No click found

    # ---------- mouse events ----------
    def on_mouse_down(self, event):
        # determine if clicking on a box
        name, mode = self.find_box_at(event.x, event.y)
        self.selected_box = name
        self.drag_mode = mode
        self.drag_start = (event.x, event.y)
        if name:
            # Keep a copy of the original box so we can calculate differences.
            self.box_start = list(self.box_objects[name])
        self.redraw()

    def on_mouse_drag(self, event):
        # Handle dragging/resizing of selected box while mouse is held down
        if not self.selected_box or not self.drag_mode:
            return
        # Convert mouse movement in screen to image coords
        dx = (event.x - self.drag_start[0]) / self.scale
        dy = (event.y - self.drag_start[1]) / self.scale
        x, y, w, h = self.box_start
        # apply drag/resize
        if self.drag_mode == "move":
            x += dx
            y += dy
        elif self.drag_mode == "resize_tl":
            x += dx
            y += dy
            w -= dx
            h -= dy
        elif self.drag_mode == "resize_tr":
            y += dy
            w += dx
            h -= dy
        elif self.drag_mode == "resize_bl":
            x += dx
            w -= dx
            h += dy
        elif self.drag_mode == "resize_br":
            w += dx
            h += dy

        w = max(w, 8)
        h = max(h, 8)
        self.box_objects[self.selected_box] = [x, y, w, h]
        self.redraw()

    def on_mouse_up(self, event):
        """
        When the mouse is released, stop dragging.
        AOI positions remain in self.box_objects until the user saves them.
        """
        self.drag_mode = None

    # ---------- preprocessing helpers ----------
    def receipt_preprocess_pil(self, pil_crop, strong=False):
        """
        Preprocess a crop for OCR.
        strong=True is used for faint numeric fields (TOTAL, quantities, prices).
        strong-False for general text fields (supplier, item description, etc).
        """
        cv_img = np.array(pil_crop)

        # CLAHE for contrast
        # Convert from RGB to LAB for L channel.
        lab = cv2.cvtColor(cv_img, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        
        #CLAHE
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l2 = clahe.apply(l)
        lab2 = cv2.merge((l2, a, b))
        enhanced = cv2.cvtColor(lab2, cv2.COLOR_LAB2RGB)

        # grayscale + denoise
        gray = cv2.cvtColor(enhanced, cv2.COLOR_RGB2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, h=10)

        if strong:
            # Numeric fields: apply slight blur to reduce noise
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
        else:
            # Normal text: morphological open to remove small speckles without blurring too much
            kernel = np.ones((3, 3), np.uint8)
            gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)

        # Otsu threshold (grayscale to black/white mask)
        _, thresh = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        if strong:
            # numeric fields only, slightly dilate the characters
            kernel = np.ones((2, 2), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=1)

        processed = Image.fromarray(thresh)
        
        # upscale for better OCR accuracy
        scale = 3 if strong else 2 # bigger scale for numeric fields
        processed = processed.resize(
            (processed.width * scale, processed.height * scale),
            Image.LANCZOS,
        )
        return processed

    # ---------- preview crops ----------
    def preview_crops(self):
        if not self.img:
            messagebox.showwarning("Warning", "Load an image first.")
            return

        preview = tk.Toplevel(self.root)
        preview.title("Crop Preview — Original + Processed")
        preview.geometry("1200x800")

        row = 0 # grid row counter
        for name, (x, y, w, h) in self.box_objects.items():
            # crop original
            img_w, img_h = self.img.size
            x2 = int(max(0, min(img_w, x + w)))
            y2 = int(max(0, min(img_h, y + h)))
            x1 = int(max(0, min(img_w, x)))
            y1 = int(max(0, min(img_h, y)))
            if x2 <= x1 or y2 <= y1: # invalid box
                continue

            crop = self.img.crop((x1, y1, x2, y2))

            strong = name.lower() in NUMERIC_FIELDS
            processed = self.receipt_preprocess_pil(crop, strong=strong)

            # thumbnails for UI
            thumb_w, thumb_h = 380, 140
            ori_thumb = crop.copy()
            ori_thumb.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
            proc_thumb = processed.copy()
            proc_thumb.thumbnail((thumb_w, thumb_h), Image.LANCZOS)

            ori_tk = ImageTk.PhotoImage(ori_thumb)
            proc_tk = ImageTk.PhotoImage(proc_thumb)

            tk.Label(
                preview, text=name.upper(), font=("Arial", 11, "bold")
            ).grid(row=row, column=0, columnspan=2, pady=(8, 2))
            l1 = tk.Label(preview, image=ori_tk)
            l1.image = ori_tk
            l1.grid(row=row + 1, column=0, padx=8, pady=6)
            l2 = tk.Label(preview, image=proc_tk)
            l2.image = proc_tk
            l2.grid(row=row + 1, column=1, padx=8, pady=6)
            row += 2

    # ---------- OCR ----------
    def run_ocr(self):
        if not self.img:
            messagebox.showwarning("Warning", "Load an image first.")
            return

        try:
            import pytesseract
        except Exception as e:
            messagebox.showerror(
                "Error",
                "pytesseract not installed or cannot be imported.\n"
                "Install with `pip install pytesseract`.\n\n" + str(e),
            )
            return

        # set tesseract path if provided
        tess_cmd = self.cfg.get("tesseract_cmd", "")
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

        # --- check that Tesseract is actually available ---
        try:
            _ = pytesseract.get_tesseract_version()
        except Exception as e:
            messagebox.showerror(
                "Error",
                "Tesseract OCR is not available or the path in config.json is invalid.\n\n"
                "Please check that Tesseract is installed and that\n"
                '"tesseract_cmd" points to tesseract.exe.\n\n'
                f"Details:\n{e}"
            )
            return

        import re

        TABLE_FIELDS = [
            "item",
            "item_desc",
            "quantity",
            "satuan",
            "unit_price",
            "disc",
            "amount",
        ]

        # --- cleaners ---
        def clean_text_general(s: str) -> str:
            if not s:
                return ""
            # remove pipes and fix some common OCR glitches
            s = s.replace("|", "")
            s = s.replace("{", "[").replace("}", "]")
            s = s.replace("!", "I")
            s = re.sub(r"\[\[", "[", s)

            # brand-specific fixes 
            s = re.sub(r"\bCancos\b", "Concos", s)
            s = re.sub(r"\bConeps\b", "Concos", s)
            s = re.sub(r"\bConeos\b", "Concos", s)
            s = re.sub(r"\bO8\b(?=\s*100ML)", "Oil", s, flags=re.IGNORECASE)
            s = re.sub(r"\bVOD\b", "VCO", s)

            # keep printable ASCII only
            s = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in s)
            lines = [line.rstrip() for line in s.splitlines()]
            return "\n".join(line for line in lines if line.strip())

        def clean_text_numeric(s: str) -> str:
            if not s:
                return ""
            allowed = "0123456789.,- Rp%"
            out_lines = []
            for line in s.splitlines():
                filtered = "".join(ch for ch in line if ch in allowed)
                if filtered.strip():
                    out_lines.append(filtered.strip())
            return "\n".join(out_lines)

        columns = {}           # name -> list of lines (for table fields)
        singles = {}           # supplier/date/total, etc.

        # --- OCR for non-item table fields + header fields ---
        
        # treat each AoI as a general OCR pipeline
        for name, (x, y, w, h) in self.box_objects.items():
            field = name.lower()
            # ITEM + ITEM_DESC are handled later as a combined block
            if field in ("item", "item_desc"):
                continue

            img_w, img_h = self.img.size
            # defensive approach, clip AOI to image bounds
            x1 = int(max(0, min(img_w, x)))
            y1 = int(max(0, min(img_h, y)))
            x2 = int(max(0, min(img_w, x + w))) 
            y2 = int(max(0, min(img_h, y + h)))
            if x2 <= x1 or y2 <= y1:
                continue

            crop = self.img.crop((x1, y1, x2, y2))
            # decide whether this field should use strong preprocessing
            # as numeric fields would benefit from more aggressive denoising
            strong = field in NUMERIC_FIELDS
            processed = self.receipt_preprocess_pil(crop, strong=strong) 

            # Tesseract config
            if field in NUMERIC_FIELDS:
                tess_cfg = (  # restrict tesseract to digits and common symbols only
                    "--oem 3 --psm 6 "
                    "-c tessedit_char_whitelist=0123456789.,-Rp% " 
                )
            else: # for text columns, use default config
                tess_cfg = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

            try: 
                raw_text = pytesseract.image_to_string(processed, config=tess_cfg)
            except Exception as e:
                raw_text = ""
                print("Tesseract error in", name, ":", e)
                
            # clean text differently based on field type
            if field in NUMERIC_FIELDS:
                cleaned_block = clean_text_numeric(raw_text)
            else:
                cleaned_block = clean_text_general(raw_text)
            # store results (decide whether the cleaned text belongs to a table column or single header field)
            if field in TABLE_FIELDS:
                lines = [ln.strip() for ln in cleaned_block.splitlines() if ln.strip()]
                columns[field] = lines
            else:
                singles[field] = cleaned_block.strip()

        # --- estimate row count from numeric columns ---
        rows_hint = 0
        for f in ["amount", "quantity", "unit_price"]:
            if f in columns:
                rows_hint = max(rows_hint, len(columns[f]))

        # --- combined ITEM + DESCRIPTION block (union of item & item_desc boxes) ---
        if "item" in self.box_objects or "item_desc" in self.box_objects:
            boxes_to_union = []
            if "item" in self.box_objects:
                boxes_to_union.append(self.box_objects["item"])
            if "item_desc" in self.box_objects:
                boxes_to_union.append(self.box_objects["item_desc"])

            x_vals = [b[0] for b in boxes_to_union]
            y_vals = [b[1] for b in boxes_to_union]
            xw_vals = [b[0] + b[2] for b in boxes_to_union]
            yh_vals = [b[1] + b[3] for b in boxes_to_union]

            x = min(x_vals)
            y = min(y_vals)
            x2 = max(xw_vals)
            y2 = max(yh_vals)
            w = x2 - x
            h = y2 - y

            img_w, img_h = self.img.size
            x1 = int(max(0, min(img_w, x)))
            y1 = int(max(0, min(img_h, y)))
            x2 = int(max(0, min(img_w, x + w)))
            y2 = int(max(0, min(img_h, y + h)))
            if x2 > x1 and y2 > y1:
                crop = self.img.crop((x1, y1, x2, y2))
                processed = self.receipt_preprocess_pil(crop, strong=False)
                try:
                    raw_items = pytesseract.image_to_string(
                        processed,
                        config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
                    )
                except Exception as e:
                    raw_items = ""
                    print("Tesseract error in items block:", e)

                cleaned_items = clean_text_general(raw_items)
                joined = re.sub(r"\s+", " ", cleaned_items.strip())

                code_pat = re.compile(
                    r"(\[[A-Z0-9]{2,}-[A-Z0-9]{2,}\]|\b[A-Z0-9]{3,}-[A-Z0-9]{2,}-\d+\b)",
                    re.IGNORECASE,
                )

                parts = code_pat.split(joined)
                item_codes = []
                item_descs = []
                for i in range(1, len(parts), 2):
                    code = parts[i].strip()
                    desc = parts[i + 1].strip() if i + 1 < len(parts) else ""
                    if code or desc:
                        item_codes.append(code)
                        item_descs.append(desc)

                # fallback: line-based split if regex fails
                if not item_codes and cleaned_items:
                    lines = [
                        ln.strip()
                        for ln in cleaned_items.splitlines()
                        if ln.strip()
                    ]
                    for ln in lines:
                        tokens = ln.split(maxsplit=1)
                        if not tokens:
                            continue
                        code = tokens[0]
                        desc = tokens[1] if len(tokens) > 1 else ""
                        item_codes.append(code)
                        item_descs.append(desc)

                if item_codes:
                    columns["item"] = item_codes
                    columns["item_desc"] = item_descs
                    rows_hint = max(rows_hint, len(item_codes))

        # --- handle satuan / disc if they come in one line like "BTL BTL" or "14 14" ---
        if rows_hint > 0 and "satuan" in columns:
            # handle cases where satuan is a single line with multiple values
            lines = columns["satuan"]
            if len(lines) == 1 and rows_hint > 1:
                # split by whitespace
                tokens = lines[0].split()
                if len(tokens) >= rows_hint:
                    columns["satuan"] = tokens[:rows_hint]

        if rows_hint > 0 and "disc" in columns:
            # handle cases where disc is a single line with multiple values
            lines = columns["disc"]
            if len(lines) == 1 and rows_hint > 1:
                # split by numbers
                tokens = re.findall(r"\d+[,.\d]*", " ".join(lines))
                if len(tokens) >= rows_hint:
                    columns["disc"] = tokens[:rows_hint]

        # --- ensure all table columns exist ---
        if not all(f in columns for f in TABLE_FIELDS):
            messagebox.showwarning(
                "Warning",
                "Not all table columns have OCR data. Check your boxes & image."
            )
            return

        # --- normalise column lengths ---
        max_rows = max(len(columns[f]) for f in TABLE_FIELDS)
        for f in TABLE_FIELDS:
            col = columns[f]
            if len(col) < max_rows: # pad with empty strings
                col = col + [""] * (max_rows - len(col))
            columns[f] = col

        # --- build table structure for editing/export ---
        header = ["ITEM", "DESCRIPTION", "QTY", "SATUAN", "UNIT_PRICE", "DISC", "AMOUNT"]
        rows = []
        for i in range(max_rows): # for each row
            row = [
                columns["item"][i],
                columns["item_desc"][i],
                columns["quantity"][i],
                columns["satuan"][i],
                columns["unit_price"][i],
                columns["disc"][i],
                columns["amount"][i],
            ]
            rows.append(row)

        meta = {
            "supplier": singles.get("supplier", ""),
            "date": singles.get("date", ""),
            "total": singles.get("total", ""),
        }

        self.last_table = {
            "header": header,
            "rows": rows,
            "meta": meta,
        }

        self.show_edit_window()

    # ---------- edit & export window ----------
    def show_edit_window(self):
        if not self.last_table:
            messagebox.showwarning("Warning", "No OCR data to edit.")
            return

        # destroy old edit window if still open
        if self.edit_win is not None and self.edit_win.winfo_exists():
            self.edit_win.destroy()

        table = self.last_table

        win = tk.Toplevel(self.root)
        win.title("Edit OCR Data & Export")
        win.geometry("1000x600")
        self.edit_win = win

        container = tk.Frame(win)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        # --- meta fields (supplier, date, total) ---
        meta_frame = tk.Frame(container)
        meta_frame.pack(anchor="w", pady=(0, 10))

        self.meta_entries = {}
        row_meta = 0
        for label, key in [("Supplier", "supplier"),
                           ("Date", "date"),
                           ("Total", "total")]:
            tk.Label(meta_frame, text=label + ":", width=10, anchor="w").grid(
                row=row_meta, column=0, sticky="w", pady=2
            )
            e = tk.Entry(meta_frame, width=60)
            e.grid(row=row_meta, column=1, sticky="w", pady=2)
            e.insert(0, table["meta"].get(key, ""))
            self.meta_entries[key] = e
            row_meta += 1

        # --- table grid ---
        table_frame = tk.Frame(container)
        table_frame.pack(fill="both", expand=True)

        header = table["header"]
        rows = table["rows"]

        # header row
        for j, head in enumerate(header):
            tk.Label(
                table_frame,
                text=head,
                font=("Consolas", 10, "bold"),
                borderwidth=1,
                relief="solid",
                padx=4,
                pady=2,
            ).grid(row=0, column=j, sticky="nsew")

        # table cells
        self.table_entries = []
        for i, row in enumerate(rows):
            row_entries = []
            for j, val in enumerate(row):
                # slightly wider entry for description
                width = 30 if j == 1 else 12
                e = tk.Entry(table_frame, width=width)
                e.grid(row=i + 1, column=j, padx=1, pady=1, sticky="nsew")
                e.insert(0, str(val))
                row_entries.append(e)
            self.table_entries.append(row_entries)

        # make columns expand nicely
        for j in range(len(header)):
            table_frame.grid_columnconfigure(j, weight=1)

        # --- buttons ---
        btn_frame = tk.Frame(container)
        btn_frame.pack(fill="x", pady=(10, 0))

        tk.Button(
            btn_frame,
            text="Export to Excel (.xlsx)",
            command=self.export_to_excel,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="Close",
            command=win.destroy,
        ).pack(side="right")

    def export_to_excel(self):
        if not self.last_table or not self.table_entries:
            messagebox.showwarning("Warning", "No table data to export.")
            return

        # update table data from the Entry widgets
        rows = []
        for row_entries in self.table_entries:
            rows.append([e.get() for e in row_entries])

        meta = {}
        for key, entry in self.meta_entries.items():
            meta[key] = entry.get()

        self.last_table["rows"] = rows
        self.last_table["meta"] = meta

        # ask for save path
        path = filedialog.asksaveasfilename(
            title="Save Excel file",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not path:
            return

        try:
            from openpyxl import Workbook
        except ImportError:
            messagebox.showerror(
                "Error",
                "openpyxl is not installed.\nInstall it with:\n\npip install openpyxl",
            )   
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Invoice"

        # write meta
        ws.cell(row=1, column=1, value="Supplier")
        ws.cell(row=1, column=2, value=meta.get("supplier", ""))
        ws.cell(row=2, column=1, value="Date")
        ws.cell(row=2, column=2, value=meta.get("date", ""))
        ws.cell(row=3, column=1, value="Total")
        ws.cell(row=3, column=2, value=meta.get("total", ""))

        # write table
        start_row = 5
        header = self.last_table["header"]
        for j, head in enumerate(header, start=1):
            ws.cell(row=start_row, column=j, value=head)

        for i, row in enumerate(rows, start=start_row + 1):
            for j, val in enumerate(row, start=1):
                ws.cell(row=i, column=j, value=val)

        try:
            wb.save(path)
        except Exception as e:
            messagebox.showerror("Error", f"Could not save Excel file:\n{e}")
            return

        messagebox.showinfo("Saved", f"Excel file saved:\n{path}")


# ----------------- run app -----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = ReceiptApp(root)
    root.geometry("1100x820")
    root.mainloop()
