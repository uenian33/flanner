Three screenshots, taken on a real iPhone, for the add-to-home-screen card:

  share.png  the share sheet, with Copy / Add to Bookmarks / Add to Reading List
  more.png   the rest of that list, down to Add to Home Screen
  menu.png   Add to Home Screen chosen

Any of .png .jpg .jpeg .heic. Drop them in and rebuild — `scripts/a2hs.py`
resizes each to 640 and 960 wide, writes WebP with one JPEG fallback, strips
the metadata a screenshot carries, and `build_home.py` writes the markup with
the source's own shape so the card does not jump as they load. A file that is
not here is a step with words and no picture; nothing breaks.

The sources stay out of the built site — only the resized copies are served.
