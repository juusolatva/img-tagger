# Image Tagging Glossary

img tagger describes images with model-generated tags stored in the images' own metadata. This glossary names the images, tagging results and metadata operations in that workflow.

## Language

### Images and tags

**Supported image format**:
An image format that img tagger can inspect and write metadata to (JPEG, WebP, PNG and GIF); other formats, such as BMP, TIFF or MPO (multi-picture JPEGs from some cameras), cannot be tagged.
_Avoid_: Valid image format (formats like BMP are valid image formats, but unsupported)

**Image candidate**:
A file selected for consideration because its extension is associated with a supported image format; its contents may still be invalid or in an unsupported format.
_Avoid_: Valid image, supported image (before checking the contents)

**Source image**:
The image file selected for tagging or metadata clearing, including its pixels, animation and existing metadata.
_Avoid_: Original (when it could also mean the copy sent to the model)

**Model image**:
The representation of a source image sent to the model for tag generation, which may be a prepared copy of its first frame or the unchanged source contents.
_Avoid_: Resized original, thumbnail (the representation may be full-sized, unscaled source contents)

**Prompt**:
The text instructions supplied to the model to guide tag generation, describing the expectations for tag language, formatting and subject emphasis.
_Avoid_: System prompt (both backends send it as a user message)

**Model reply**:
The text the model returns for a model image and prompt, from which the tag list is parsed; it may contain reasoning, formatting or other text besides the tags.
_Avoid_: Tags, tag list (before parsing and normalization)

**Tag**:
A descriptive keyword or phrase associated with an image, such as a subject, image type, mood or visible text; its language and wording depend on the prompt and model reply.
_Avoid_: Label, category (when referring to an individual tag)

**Tag list**:
The ordered collection of six to twelve distinct, lowercase tags accepted for an image, with surrounding whitespace removed; when the model reply contains more than twelve, the first twelve are kept.
_Avoid_: Tag set (order is preserved)

**Tag generation**:
The model's production of a model reply proposing tags for a model image under the supplied prompt.
_Avoid_: Tagging (when no metadata has been written)

**Tagging**:
The operation of obtaining a tag list from a model and writing it with a processing marker into a source image's metadata.
_Avoid_: Tag generation (when the metadata write is also meant)

**Processing marker**:
The text `[PROCESSED BY AI]` used to recognize an image as already processed, regardless of the tags it contains or whoever wrote it.
_Avoid_: Tag, proof of successful tagging (indicates prior processing, not tag validity)

### Tagging outcomes

**Tagging run**:
One invocation of img tagger that tags the image candidates of a folder, ending when every candidate has an outcome.
_Avoid_: Session, batch

**Stop request**:
The user's request, by pressing `Q`, to end a tagging run early; images whose tag generation has begun finish, and images that still need tag generation are cancelled.
_Avoid_: Abort, interrupt (in-flight images are not interrupted)

**Tagged**:
The outcome of successfully writing a generated tag list and processing marker to an image during the current tagging run.
_Avoid_: Processed (without qualification; the report's `Processed images` label is the established exception and counts only tagged images)

**Skipped**:
The outcome for an image whose metadata already contains a processing marker, left unchanged during the current tagging run.
_Avoid_: Failed, cancelled

**Failed**:
An unsuccessful tagging outcome caused by an unreadable or unsupported image, a failed model request, a model reply with fewer than six usable tags (including an unparseable reply) or a failed metadata write.
_Avoid_: Skipped (for an invalid image)

**Cancelled**:
The outcome for an image whose tag generation was withheld because a stop request was observed before generation began.
_Avoid_: Skipped, failed

### Metadata operations

**Metadata clearing**:
Removal of all EXIF, XMP and IPTC metadata from a JPEG, WebP or PNG, or of the comment from a GIF, including information unrelated to generated tags. JPEG comments and PNG text chunks are kept, so a processing marker stored there still causes a skip, and every GIF is re-encoded.
_Avoid_: Undo tagging, reset tags, remove all metadata

**Metadata repair**:
Re-saving a source image without its unreadable metadata so that an edit can proceed; JPEG and WebP images are re-encoded, and existing metadata is lost.
_Avoid_: Auto-healing, sanitization (implementation terms)
