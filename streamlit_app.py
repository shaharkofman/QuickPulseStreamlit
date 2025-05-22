
import streamlit as st
from openai import OpenAI
from supabase import create_client, Client
import pandas as pd
import altair as alt
import json, uuid, qrcode, time
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
                    {"role": "system", "content": "You are a helpful quiz generator. Respond with a JSON array of 3 MCQs, each with explanation."},
                    {"role": "user", "content": f"""Generate 3 multiple choice questions on {topic} with explanations.
Format:
[
  {{
    \"question\": \"...\",
    \"options\": [\"A\", \"B\", \"C\", \"D\"],
    \"answer\": \"B\",
    \"explanation\": \"...\"
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

                quiz_id = str(uuid.uuid4())
                supabase.table("quizzes").insert({
                    "quiz_id": quiz_id,
                    "topic": topic,
                    "questions": parsed
                }).execute()

                quiz_link = f"{st.secrets['APP_BASE_URL']}?quiz_id={quiz_id}"
                st.write("📌 Quiz Link:", quiz_link)
                show_qr(quiz_link)

            except json.JSONDecodeError:
                st.error("Invalid response from OpenAI.")

    if st.checkbox("View Results"):
        quizzes = supabase.table("quizzes").select("*").order("created_at", desc=True).limit(5).execute().data
        for q in quizzes:
            st.subheader(f"{q['topic']} (ID: {q['quiz_id'][:8]})")
            res = supabase.table("quiz_results").select("*").eq("quiz_id", q["quiz_id"]).execute().data
            if not res:
                st.info("No responses yet.")
                continue
            st.write(f"📊 {len(res)} submissions")
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

    if quiz_id and name:
        prior = supabase.table("quiz_results").select("id").eq("quiz_id", quiz_id).eq("student_id", name).execute().data
        if prior:
            st.warning("You have already submitted this quiz.")
        else:
            quiz_data = supabase.table("quizzes").select("*").eq("quiz_id", quiz_id).execute().data
            if not quiz_data:
                st.error("Invalid or expired quiz link.")
            else:
                questions = quiz_data[0]["questions"]
                answers = {}

                with st.form("quiz_form"):
                    timer = st.number_input("Optional: Set a time limit (seconds)", value=0, step=10)
                    start = time.time()

                    for i, q in enumerate(questions):
                        st.subheader(f"Q{i+1}: {q['question']}")
                        choice = st.radio("Your answer:", q["options"], key=f"q_{i}")
                        answers[q["question"]] = {"selected": choice, "correct": q["answer"], "explanation": q["explanation"]}

                    submitted = st.form_submit_button("Submit All")
                    if submitted:
                        elapsed = time.time() - start
                        if timer > 0 and elapsed > timer:
                            st.error("⏱ Time's up! Your answers were not submitted.")
                        else:
                            score = 0
                            for q_text, data in answers.items():
                                correct = data["selected"] == data["correct"]
                                if correct: score += 1
                                st.markdown(f"**Q:** {q_text}")
                                st.markdown(f"- Your answer: `{data['selected']}`")
                                st.markdown(f"- Correct: `{data['correct']}`")
                                st.markdown(f"- Explanation: {data['explanation']}")
                                st.markdown("---")
                                supabase.table("quiz_results").insert({
                                    "id": str(uuid.uuid4()),
                                    "student_id": name,
                                    "quiz_id": quiz_id,
                                    "question_text": q_text,
                                    "correct_answer": data["correct"],
                                    "student_answer": data["selected"],
                                    "is_correct": correct,
                                    "timestamp": datetime.utcnow().isoformat()
                                }).execute()
                            st.success(f"Final Score: {score} / {len(questions)}")
    else:
        st.info("Enter your name and use a valid quiz link to proceed.")
