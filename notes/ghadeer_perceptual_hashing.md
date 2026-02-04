Date: Jan 23 2026

Duplicate Image Detection

* One algorithm that compares images is **Perceptual Hashing** but what does this algorithm actually do?

**Perceptual Hashing creates a "fingerprint" for images:**
- Converts image to small grayscale for example (8X8 pixels)
- Compares each pixel to average brightness
- Creates binary code: 1 = brighter, 0 = darker
- Result = 64-bit hash (fingerprint)

**Why it's better than regular hashing:**
- Regular hash: Change 1 pixel → completely different hash 
- Perceptual hash: Minor changes (compression, brightness) → same hash 
- Wildlife cameras take 5 burst shots of same scene → perceptual hash identifies them as duplicates even though they're technically different files

**Don't be scared by this because Python libraries got us covered**
- imagehash
- Install: pip install imagehash pillow
- You will need a hamming distance (difference = hash1 - hash2) & a threshold (if difference < 10:)
- **Note:** This step reads from the existing data/staging/

**Youtube Videos about Perceptual Hashing:**
- [Perceptual Hashing To Compare Images Explained
](https://youtu.be/IJ-QjDCaz-o?si=Wu2bWYVE3zisQ-2l)
- [Perceptual Hash - Harold | Python OpenCV
](https://youtu.be/SFoE6_o0mhE?si=-M_LMN13aT64bzhC)
- [Applied Hashes: Perceptual and Cryptographic
](https://youtu.be/1lubZl1ccC4?si=WFrDoWy4z7VbLP-L)

![Perceptual Hashing](Blockhash-perceptual-hashing-method-overview.png)