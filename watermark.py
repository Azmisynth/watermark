import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import os

# ── Configuration ──────────────────────────────────────────────────────────────
COVER_IMAGE_PATH = "image.jpeg"
RESULTS_DIR = "results"
WATERMARK_SEED = 42          # Fixed seed so we can regenerate same watermark
WATERMARK_SIZE = (64, 64)    # Height x Width of watermark in pixels
QUALITY_FACTORS = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]

os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Step 1: Create binary watermark ───────────────────────────────────────────
def create_watermark(size, seed):
    """Generate a reproducible random binary watermark (values: 0 or 1)."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2, size=size, dtype=np.uint8)

watermark = create_watermark(WATERMARK_SIZE, WATERMARK_SEED)

# Save watermark for visual reference (scale 0/1 → 0/255 so it's visible)
wm_img = Image.fromarray(watermark * 255)
wm_img.save(os.path.join(RESULTS_DIR, "watermark_original.png"))
print(f"Watermark shape: {watermark.shape}  |  Unique values: {np.unique(watermark)}")

# ── Step 2: Load cover image ───────────────────────────────────────────────────
cover_img = Image.open(COVER_IMAGE_PATH).convert("RGB")
cover_array = np.array(cover_img, dtype=np.uint8)
print(f"Cover image shape: {cover_array.shape}")   # e.g. (1080, 810, 3)

# ── Step 3: Embed watermark into LSB of Red channel ───────────────────────────
def embed_lsb(cover, wm):
    """
    Embed binary watermark wm (H x W) into the LSB of the Red channel
    of cover image (H_img x W_img x 3).
    Returns a new array — does not modify cover in place.
    """
    wm_h, wm_w = wm.shape
    assert cover.shape[0] >= wm_h and cover.shape[1] >= wm_w, \
        "Watermark is larger than cover image"

    watermarked = cover.copy()
    # Clear LSB of Red channel in the watermark region, then set watermark bit
    watermarked[:wm_h, :wm_w, 0] = (cover[:wm_h, :wm_w, 0] & 0xFE) | wm
    return watermarked

watermarked_array = embed_lsb(cover_array, watermark)

# Save lossless PNG so we can inspect embedding without JPEG noise
watermarked_lossless = Image.fromarray(watermarked_array)
watermarked_lossless.save(os.path.join(RESULTS_DIR, "watermarked_lossless.png"))
print("Watermark embedded. Lossless copy saved.")

# ── Step 4: Extract watermark from LSB of Red channel ─────────────────────────
def extract_lsb(img_array, wm_shape):
    """
    Extract the LSB of the Red channel from the top-left wm_shape region.
    Returns a binary array of shape wm_shape.
    """
    wm_h, wm_w = wm_shape
    return img_array[:wm_h, :wm_w, 0] & 0x01

# Quick sanity check: extract from the lossless watermarked image
extracted_lossless = extract_lsb(watermarked_array, WATERMARK_SIZE)
ber_lossless = np.mean(extracted_lossless != watermark)
print(f"BER (lossless, no compression): {ber_lossless:.4f}  <- should be 0.0000")

# ── Step 5: JPEG compression at each QF, then extract and measure BER ─────────
ber_results = {}   # QF -> BER

for qf in QUALITY_FACTORS:
    # Save watermarked image as JPEG at this quality factor
    compressed_path = os.path.join(RESULTS_DIR, f"watermarked_qf{qf}.jpg")
    Image.fromarray(watermarked_array).save(compressed_path, format="JPEG", quality=qf)

    # Reload from disk (simulates what an attacker / evaluator would do)
    compressed_array = np.array(Image.open(compressed_path).convert("RGB"), dtype=np.uint8)

    # Extract watermark
    extracted = extract_lsb(compressed_array, WATERMARK_SIZE)

    # Save extracted watermark image (scale to 0/255 for visibility)
    extracted_img = Image.fromarray(extracted * 255)
    extracted_img.save(os.path.join(RESULTS_DIR, f"extracted_qf{qf}.png"))

    # Calculate BER
    ber = np.mean(extracted != watermark)
    ber_results[qf] = ber
    print(f"QF={qf:3d}  |  BER={ber:.4f}  |  {'WATERMARK DESTROYED (BER>=0.45)' if ber >= 0.45 else 'Watermark surviving'}")

# ── Step 6: Plot BER vs QF ─────────────────────────────────────────────────────
qf_values = list(ber_results.keys())
ber_values = list(ber_results.values())

plt.figure(figsize=(10, 5))
plt.plot(qf_values, ber_values, marker="o", color="steelblue", linewidth=2, markersize=8)
plt.axhline(y=0.5, color="red", linestyle="--", label="BER=0.5 (random, fully destroyed)")
plt.axhline(y=0.0, color="green", linestyle="--", label="BER=0.0 (perfect extraction)")
plt.xlabel("JPEG Quality Factor (QF)", fontsize=13)
plt.ylabel("Bit Error Rate (BER)", fontsize=13)
plt.title("LSB Watermark Robustness vs JPEG Quality Factor", fontsize=14)
plt.xticks(qf_values)
plt.ylim(-0.05, 0.6)
plt.grid(True, alpha=0.4)
plt.legend()
plt.tight_layout()
plot_path = os.path.join(RESULTS_DIR, "ber_vs_qf.png")
plt.savefig(plot_path, dpi=150)
plt.close()
print(f"\nPlot saved to {plot_path}")

# ── Summary table ──────────────────────────────────────────────────────────────
print("\n=== SUMMARY ===")
print(f"{'QF':>5} | {'BER':>8} | Status")
print("-" * 35)
for qf in qf_values:
    ber = ber_results[qf]
    status = "DESTROYED" if ber >= 0.45 else ("Degraded" if ber > 0.1 else "OK")
    print(f"{qf:>5} | {ber:>8.4f} | {status}")
