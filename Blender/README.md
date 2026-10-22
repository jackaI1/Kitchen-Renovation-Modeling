# Blender scene and support

`Kitchen_Renovation.blend` is the current selected-B coordination model. It opens at the first frame of the walkthrough and contains organized, editable collections and seven packed image assets.

The repository's embedded walkthrough was rendered from this model and includes the pocket-door, backsplash and pullout corrections summarized in the main project README.

## Reproduce the walkthrough

Unzip `Support.zip` beside the `.blend` file. The portable scripts require Blender 5.2.2 LTS with Metal GPU support, Python 3 with Pillow, FFmpeg/FFprobe and macOS Helvetica for the lighting captions.

```sh
blender -b Kitchen_Renovation.blend --python Support/scripts/render_frames.py -- --output frames
python3 Support/scripts/encode_frames.py --frames frames --output Kitchen_Walkthrough.mp4
```

The preset uses Cycles at 1920 × 1080, 24 fps and 1,104 native frames: 64 maximum samples, adaptive sampling and denoising. Rendering resumes only from frames that match the saved scene and settings contract. The encoder adds the three lighting-comparison captions and exports an H.264 video.

## Inspect the changed mechanisms

```sh
blender -b Kitchen_Renovation.blend --python Support/scripts/check_changed_fit.py
```

This performs scoped, sampled travel checks for the revised pullouts and pocket door, restores diagnostic poses and writes audit results without saving scene changes. The archive also includes geometry scripts and selected rendered evidence. Reference documents, supplied photographs, source summaries and private correspondence are excluded.

Organizer geometry and hardware are proposed coordination details. Verify actual products, loads, stone templates and field dimensions before fabrication.
