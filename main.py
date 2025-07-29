from app.tracker import add_expense

def main():
    print("Welcome to ExpenX")
    amount = float(input("Enter amount spent: ₹"))
    description = input("Enter description: ")
    date = input("Enter date (YYYY-MM-DD) [Leave blank for today]: ") or None
    
    add_expense(amount, description, date)

if __name__ == "__main__":
    main()
