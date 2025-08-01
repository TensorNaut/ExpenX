import cv2
import pytesseract
import re
from datetime import datetime


def extract_details(image_path):
    import pytesseract
    import cv2
    import re
    from PIL import Image
    from datetime import datetime
    import numpy as np

    image = cv2.imread(image_path)

    # Convert to grayscale and apply threshold
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # OCR Extraction
    custom_config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(thresh, config=custom_config)

    # Extract date (formats like 30 Jul 2025)
    date_match = re.search(r'(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})', text)
    date = None
    if date_match:
        try:
            date = datetime.strptime(date_match.group(0), '%d %b %Y').date().isoformat()
        except ValueError:
            pass

    # Extract amount - get all ₹ values and pick the largest
    amount_match = re.search(r'(?:₹|Rs\.?|INR)?\s?(\d{1,4}(?:[.,]\d{2})?)', text)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None

    # Extract description using 'TO' or nearest meaningful line
    lines = text.split('\n')
    desc_line = next((line.strip() for line in lines if 'TO ' in line.upper()), '')
    if not desc_line:
        # fallback: longest line or line with alphanumeric majority
        desc_line = max(lines, key=lambda l: sum(c.isalnum() for c in l.strip()), default='').strip()

    # Package the result
    result = {
        "description": desc_line,
        "amount": amount,
        "date": date
    }
    result
    print(result)


pt = r"C:/Users/Tushar/Downloads/trans1.jpg"
details = extract_details(pt)