# LV Scout pitch deck

`print.html` is the 16:9 pitch (1440×810 pt). Screenshots sit on the slide with a light shadow, without a grey frame. Vault and Plans/Upgrade are included.

Print:

```bash
google-chrome --headless=new --disable-gpu --no-pdf-header-footer --no-margins \
  --print-to-pdf=LV-Scout-Pitch.pdf --allow-file-access-from-files \
  "file://$PWD/print.html"
```

The CSS sets `@page { size: 1440pt 810pt }` and scales each 1440×810 slide to that paper size.
