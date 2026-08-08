Three screenshots, taken on a real iPhone, for the add-to-home-screen card.
These are the masters. Keep them: the served copies are small and cannot be
enlarged again, so losing these means going back to a phone and re-shooting.

  menu.webp   Safari's page menu, with Share above Add to Bookmarks
  share.webp  the share sheet's bottom row, ending in View More
  home.webp   the rest of that list, down to Add to Home Screen

The stem is what matters, not the extension — `scripts/a2hs.py` matches
`menu`, `share` and `home` against whatever file carries that name, so any of
.webp .png .jpg .jpeg .heic will do. Drop one in and rebuild.

They are WebP at quality 92 rather than the JPEGs they arrived as, which is
271 KB down to 109 KB for the three. That is a second lossy pass over an
already-lossy screenshot, which would be the wrong thing to do to a master you
intend to print — but these are only ever downscaled to 400 and 600 wide and
re-encoded at 82, and the delivered images measure an RMS difference of at
most 1.94 out of 255 against the ones built from the JPEGs. Under 1% and
invisible, and the served files are the same size to the kilobyte.

`a2hs.py` resizes each to 400 and 600 wide, writes WebP with one JPEG
fallback, and strips the metadata a screenshot carries — a screenshot records
the device and, on some phones, where it was taken. `build_home.py` writes the
markup with the source's own shape, so the card does not jump as the pictures
load. A step whose file is missing is a step with words and no picture;
nothing breaks.

The sources stay out of the built site — only the resized copies are served.

The three here came off an iPhone in Downloads/guidance (IMG_0576, IMG_0577,
IMG_0578) and were renamed for the step each one shows.
