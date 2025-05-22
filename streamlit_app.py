import streamlit as st
from openai import OpenAI
from supabase import create_client, Client
import pandas as pd
import altair as alt
import json
import uuid
from datetime import datetime

# ====== CONFIG ======
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(supabase_url, supabase_key)

# ====== SESSION ======
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "mode" not in st.session_state:
    st.session_state.mode = "student"

# ====== HEADER ======
st.title("QuickPulse AI Quiz System")

mode = st.radio("Choose mode:", ["Student", "Teacher"])
st.session_state.mode = mode.lower()

# ====== STUDENT MODE ======
if st.session_state.mode == "student":
    name = st.text_input("Enter your name:")
    topic = st.text_input("Enter a topic (e.g. Fractions)")

    if st.button("Generate Quiz"):
        with st.spinner("Generating quiz..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful quiz generator. Always respond ONLY in strict JSON format."},
                        {"role": "user", "content": f"""Generate 3 multiple choice questions about {topic}.
Each question should be an object with:
- "question": the question string
- "options": a list of 4 choices
- "answer": the correct option string

Respond ONLY as a JSON array like this:

[
  {{
    "question": "What is 2+2?",
    "options": ["1", "2", "3", "4"],
    "answer": "4"
  }},
  ...
]"""}
                    ]
                )
                content = response.choices[0].message.content
                st.code(content, language="json")
                st.session_state.quiz = json.loads(content)
            except json.JSONDecodeError:
                st.error("⚠️ Failed to parse AI response. Try again or check format.")
            except Exception as e:
                st.error(f"OpenAI Error: {e}")

    for i, q in enumerate(st.session_state.quiz):
        st.subheader(f"Q{i+1}: {q['question']}")
        choice = st.radio("Choose:", q["options"], key=f"q_{i}")

        if st.button(f"Submit Q{i+1}", key=f"submit_{i}"):
            is_correct = (choice == q["answer"])
            st.success("✅ Correct!" if is_correct else f"❌ Wrong! Correct answer: {q['answer']}")
            supabase.table("quiz_results").insert({
                "id": str(uuid.uuid4()),
                "student_id": name or "anonymous",
                "question_text": q["question"],
                "correct_answer": q["answer"],
                "student_answer": choice,
                "is_correct": is_correct,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()

# ====== TEACHER MODE ======
if st.session_state.mode == "teacher":
    st.header("📊 Class Performance Heatmap")
    res = supabase.table("quiz_results").select("*").execute()
    df = pd.DataFrame(res.data)

    if df.empty:
        st.info("No data yet.")
    else:
        pivot = df.pivot_table(index="student_id", columns="question_text", values="is_correct", aggfunc="max")
        chart_df = pivot.reset_index().melt(id_vars="student_id", var_name="question", value_name="correct")

        chart = alt.Chart(chart_df).mark_rect().encode(
            x=alt.X("question:N", title="Question"),
            y=alt.Y("student_id:N", title="Student"),
            color=alt.Color("correct:N", scale=alt.Scale(domain=[True, False], range=["green", "red"]))
        ).properties(width=600)

        st.altair_chart(chart, use_container_width=True)
