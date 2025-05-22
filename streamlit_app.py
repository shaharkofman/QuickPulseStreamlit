import streamlit as st
from openai import OpenAI
from supabase import create_client, Client
import pandas as pd
import altair as alt
import json, uuid, qrcode
from io import BytesIO
from datetime import datetime

# === Setup ===
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

st.title("QuickPulse – AI Quiz System")

mode = st.radio("Choose mode:", ["Teacher", "Student"])

# === QR Code Helper ===
def show_qr(link):
    qr = qrcode.make(link)
    buf = BytesIO()
    qr.save(buf)
    st.image(buf.getvalue(), caption="Scan this QR to answer the quiz")

# === Teacher Mode ===
if mode == "Teacher":
    topic = st.text_input("Enter topic (e.g. Fractions)")
    if st.button("Generate AI Quiz"):
        with st.spinner("Creating quiz..."):
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful quiz generator. Respond with a JSON array of 3 MCQs."},
                    {"role": "user", "content": f"""Generate 3 multiple choice questions on {topic}. Format:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "B"
  }},
  ...
]"""}
                ]
            )
            quiz_json = response.choices[0].message.content
            try:
                parsed = json.loads(quiz_json)
                st.success("Quiz created!")
                st.write(parsed)

                # Save quiz to DB
                quiz_id = str(uuid.uuid4())
                supabase.table("quizzes").insert({
                    "quiz_id": quiz_id,
                    "topic": topic,
                    "questions": parsed
                }).execute()

                quiz_link = f"{st.secrets['APP_BASE_URL']}?quiz_id={quiz_id}"
                st.write("📎 Quiz Link:", quiz_link)
                show_qr(quiz_link)

            except json.JSONDecodeError:
                st.error("Invalid response from OpenAI.")

    # Optional: show past quizzes & heatmap
    if st.checkbox("View Results"):
        quizzes = supabase.table("quizzes").select("*").order("created_at", desc=True).limit(5).execute().data
        for q in quizzes:
            st.subheader(f"{q['topic']} (ID: {q['quiz_id'][:8]})")
            res = supabase.table("quiz_results").select("*").eq("quiz_id", q["quiz_id"]).execute().data
            if not res:
                st.info("No responses yet.")
                continue
            df = pd.DataFrame(res)
            pivot = df.pivot_table(index="student_id", columns="question_text", values="is_correct", aggfunc="max")
            melted = pivot.reset_index().melt(id_vars="student_id", var_name="question", value_name="correct")
            chart = alt.Chart(melted).mark_rect().encode(
                x="question:N",
                y="student_id:N",
            color=alt.Color("correct:N", scale=alt.Scale(domain=[True, False], range=["green", "red"]))
            ).properties(width=600)
            st.altair_chart(chart)

# === Student Mode ===
if mode == "Student":
    query_params = st.experimental_get_query_params()
    quiz_id = query_params.get("quiz_id", [None])[0]
    name = st.text_input("Enter your name:")

    if quiz_id:
        quiz_data = supabase.table("quizzes").select("*").eq("quiz_id", quiz_id).execute().data
        if not quiz_data:
            st.error("Invalid or expired quiz link.")
        else:
            questions = quiz_data[0]["questions"]
            for i, q in enumerate(questions):
                st.subheader(f"Q{i+1}: {q['question']}")
                choice = st.radio("Your answer:", q["options"], key=f"q_{i}")
                if st.button(f"Submit Q{i+1}", key=f"s_{i}"):
                    is_correct = (choice == q["answer"])
                    st.success("✅ Correct!" if is_correct else f"❌ Wrong! Answer: {q['answer']}")
                    supabase.table("quiz_results").insert({
                        "id": str(uuid.uuid4()),
                        "student_id": name or "anonymous",
                        "quiz_id": quiz_id,
                        "question_text": q["question"],
                        "correct_answer": q["answer"],
                        "student_answer": choice,
                        "is_correct": is_correct,
                        "timestamp": datetime.utcnow().isoformat()
                    }).execute()
    else:
        st.info("No quiz ID found. Please scan a QR code or use a shared link.")
