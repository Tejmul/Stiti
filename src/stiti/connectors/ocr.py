"""On-device OCR with Apple Vision (free, private, Hindi + English): screenshots and scanned PDFs."""
from __future__ import annotations

from pathlib import Path


def _recognize(cgimage) -> str:
    import Vision
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    try:
        req.setRecognitionLanguages_(["en-US", "hi-IN"])
    except Exception:
        pass
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        return ""
    lines = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if cand and len(cand):
            lines.append(str(cand[0].string()))
    return "\n".join(lines)


def ocr_image(path: str | Path) -> str:
    import Quartz
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return ""
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    return _recognize(img) if img is not None else ""


def ocr_pdf(path: str | Path, max_pages: int = 30, scale: float = 2.0) -> str:
    """Render each PDF page (Quartz) and OCR it — for scanned PDFs with no text layer."""
    import Quartz
    from Foundation import NSURL
    doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(path)))
    if doc is None:
        return ""
    pages = []
    for i in range(1, min(Quartz.CGPDFDocumentGetNumberOfPages(doc), max_pages) + 1):
        page = Quartz.CGPDFDocumentGetPage(doc, i)
        box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
        w, h = int(box.size.width * scale), int(box.size.height * scale)
        cs = Quartz.CGColorSpaceCreateDeviceRGB()
        ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
        Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
        Quartz.CGContextScaleCTM(ctx, scale, scale)
        Quartz.CGContextDrawPDFPage(ctx, page)
        img = Quartz.CGBitmapContextCreateImage(ctx)
        txt = _recognize(img)
        if txt.strip():
            pages.append(f"## Page {i}\n\n{txt}")
    return "\n\n".join(pages)
