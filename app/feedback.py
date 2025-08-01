import pandas as pd

def log_feedback(description, predicted_category, actual_category):
    feedback_file = "D:/PROJECTS/Version Control/ExpenX/data/feedback.csv"
    feedback_entry = {
        "description": description,
        "predicted_category": predicted_category,
        "actual_category": actual_category
    }

    # Append or create file
    if os.path.exists(feedback_file):
        df_feedback = pd.read_csv(feedback_file)
        df_feedback = pd.concat([df_feedback, pd.DataFrame([feedback_entry])], ignore_index=True)
    else:
        df_feedback = pd.DataFrame([feedback_entry])

    df_feedback.to_csv(feedback_file, index=False)
    print("Feedback logged ")
