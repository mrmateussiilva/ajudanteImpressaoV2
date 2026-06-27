import glob
from pathlib import Path
import json
from PIL import Image
from ajudante_impressao.algorithms.packing import pack_images_masked

# Load all cached images
cache_dir = Path("/home/mateus/Documentos/Projects/Pessoais/impressor/treinamentos/shopee/.ajudante_cache")
png_files = sorted(cache_dir.glob("*.png"))

# Let's run the packing now
images = []
for f in png_files:
    json_file = f.with_suffix(".json")
    if not json_file.exists():
        continue
    try:
        with open(json_file, "r", encoding="utf-8") as j:
            meta = json.load(j)
        img = Image.open(f)
        img.load()
        if "width_px" in meta and (meta["width_px"] != img.width or meta["height_px"] != img.height):
            img = img.resize((meta["width_px"], meta["height_px"]), Image.Resampling.LANCZOS)
        img.info["original_filename"] = meta.get("name", f.name)
        images.append(img)
    except Exception as e:
        print(f"Failed to load {f.name}: {e}")

print(f"Loaded {len(images)} images from cache.")

def progress_cb(current, total):
    print(f"Packing progress: {current}/{total}")

import time

t0 = time.time()
packed, w, h = pack_images_masked(
    images,
    max_width=4921,
    spacing=12,
    margin=20,
    step=8,
    allow_rotate=True,
    progress_cb=progress_cb,
    performance_mode="balanced"
)
t1 = time.time()
print(f"Packing took {t1 - t0:.2f} seconds.")

print(f"\nPacked Canvas: {w}x{h}px")
for i, (img, x, y) in enumerate(packed):
    orig_name = img.info.get("original_filename", "unknown")
    print(f"Peca {i} (name='{orig_name}', size={img.size}): x={x}, y={y}")

# Test DXF generation
print("\nGenerating debug DXF...")
from ajudante_impressao.services.roll_packer import _generate_roll_dxf
image_items_test = [{"image": img} for img in images]
dxf_out = Path("ajudante_impressao/scratch/debug_roll.dxf")
t2 = time.time()
try:
    _generate_roll_dxf(
        packed=packed,
        final_h=h,
        output_dxf_path=dxf_out,
        image_items=image_items_test,
        dpi=100
    )
    t3 = time.time()
    print(f"Success! DXF generated at: {dxf_out} (File size: {dxf_out.stat().st_size} bytes)")
    print(f"DXF generation took {t3 - t2:.2f} seconds.")
    
    print("\nGenerating debug contours image...")
    from ajudante_impressao.services.roll_packer import _save_debug_contours
    dbg_img_out = Path("ajudante_impressao/scratch/debug_roll_debug_contornos.png")
    _save_debug_contours(
        packed=packed,
        final_w=w,
        final_h=h,
        output_path=dbg_img_out,
        image_items=image_items_test,
    )
    print(f"Success! Debug contours image saved at: {dbg_img_out}")
except Exception as e:
    print(f"Error: {e}")
