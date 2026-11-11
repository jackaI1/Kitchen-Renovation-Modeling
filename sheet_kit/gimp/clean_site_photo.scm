; Sheet kit: clean one site photo for the title block sheet.
; Run with: gimp -i -b '(load "clean_site_photo.scm")' -b '(sheet-kit-clean-photo "in.jpg" "out.png" 1500 2.5)' -b '(gimp-quit 0)'
; Steps: open, crop to the frame aspect ratio around the centre, stretch levels,
; light unsharp mask, scale to the target width, save PNG. Written for GIMP 2.10 Script-Fu.

(define (sheet-kit-int value)
  (inexact->exact (round value)))

(define (sheet-kit-clean-photo in-path out-path target-width ratio)
  (let* ((image (car (gimp-file-load RUN-NONINTERACTIVE in-path in-path)))
         (width (car (gimp-image-width image)))
         (height (car (gimp-image-height image)))
         (crop-width (min width (sheet-kit-int (* height ratio))))
         (crop-height (min height (sheet-kit-int (/ width ratio))))
         (offset-x (sheet-kit-int (/ (- width crop-width) 2)))
         (offset-y (sheet-kit-int (/ (- height crop-height) 2)))
         (scaled-height (sheet-kit-int (/ target-width ratio))))
    (gimp-image-crop image crop-width crop-height offset-x offset-y)
    (let ((drawable (car (gimp-image-get-active-drawable image))))
      (gimp-drawable-levels-stretch drawable)
      (plug-in-unsharp-mask RUN-NONINTERACTIVE image drawable 1.0 0.5 0))
    (gimp-image-scale image (sheet-kit-int target-width) scaled-height)
    (gimp-file-save RUN-NONINTERACTIVE image (car (gimp-image-get-active-drawable image)) out-path out-path)
    (gimp-image-delete image)))
