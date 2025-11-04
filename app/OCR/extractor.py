import pytesseract
from PIL import Image

# Path to your image
image_path = r"C:\Users\Tushar\Downloads\trans1.jpg"

def extract_text_from_image(image_path):
    # Open the image
    img = Image.open(image_path)
    # Extract text
    text = pytesseract.image_to_string(img)
    # Print the extracted text
    print(text)

if __name__ == "__main__":
    extract_text_from_image(image_path)