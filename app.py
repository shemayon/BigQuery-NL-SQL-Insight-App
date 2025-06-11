import os
import streamlit as st
import pandas as pd
from google.cloud import bigquery
import openai
from utils.helper_funtions import BigQueryDatabase

st.set_page_config(page_title="GA Sample NL→SQL Explorer", layout="wide")
st.title("BigQuery Test")

# OpenAI Key from env
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    st.error("❌ Set the OPENAI_API_KEY env var before running.")
    st.stop()

# Initialize BigQueryDatabase with ADC
_default_client = bigquery.Client()
project_id = _default_client.project
location = 'US'
key_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
datasets = ['google_analytics_sample']
db = BigQueryDatabase(project_id, location, key_file, datasets)

dataset_id = "bigquery-public-data.google_analytics_sample"
table_wildcard = f"{dataset_id}.ga_sessions_*"

# Schema preview
st.markdown("**Schema preview:**")
try:
    shard = f"{dataset_id}.ga_sessions_20170801"
    tbl = db.client.get_table(shard)
    schema_df = pd.DataFrame([(f.name, f.field_type, f.mode) for f in tbl.schema], columns=["name","type","mode"])
    st.dataframe(schema_df)
except Exception as e:
    st.warning(f"Schema preview failed: {e}")
    schema_df = pd.DataFrame(columns=["name","type","mode"])

# Natural-language input
st.subheader("Ask a question about the GA data")
question = st.text_input("e.g. 'Top 10 campaigns by sessions' or 'COM% by country'")

if st.button("Generate SQL & Run"):
    if not question.strip():
        st.error("Enter a question.")
    else:
        cols = ", ".join(schema_df['name'].tolist()) if not schema_df.empty else "(columns unavailable)"
        sql_prompt = (
            "You are a BigQuery SQL expert.\n"
            f"The user has access to table `{table_wildcard}` with columns: {cols}.\n"
            "Translate the user’s request into valid BigQuery Standard SQL using the wildcard.\n"
            "Output ONLY the SQL—no explanation.\n\n"
            f"Request: {question!r}"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role":"system","content":"Generate BigQuery Standard SQL."},
                    {"role":"user","content":sql_prompt}
                ],
                temperature=0.0,
                max_tokens=200
            )
            raw_sql = resp.choices[0].message.content.strip().strip("```")
            lines = raw_sql.splitlines()
            for i, line in enumerate(lines):
                if line.strip().lower().startswith(("select","with")):
                    sql_query = "\n".join(lines[i:])
                    break
            else:
                sql_query = raw_sql
            st.subheader("🔧 Generated SQL")
            st.code(sql_query, language="sql")
        except Exception as e:
            st.error(f"OpenAI SQL gen error: {e}")
            st.stop()

        try:
            rows = db.execute_query(sql_query)
            result_df = pd.DataFrame(rows)
        except Exception as e:
            st.error(f"Query execution error: {e}")
            st.stop()

        if result_df.empty:
            st.warning("✅ No rows returned.")
        else:
            st.subheader("📋 Results")
            st.dataframe(result_df)
            with st.spinner("Generating explanation & insights..."):
                table_md = result_df.head(20).to_markdown(index=False)
                insight_prompt = (
                    "You are a data analyst. The user ran the SQL:\n```sql\n" +
                    sql_query +
                    "\n```\nIt returned this table (Markdown):\n" +
                    table_md +
                    "\n\n1. Explain in plain English what the query does.\n"
                    "2. Provide 3–5 key insights from these results."
                )
                resp2 = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[
                        {"role":"system","content":"Explain SQL and analyze data."},
                        {"role":"user","content":insight_prompt}
                    ],
                    temperature=0.5,
                    max_tokens=400
                )
                explanation = resp2.choices[0].message.content
            st.subheader("💡 Explanation & Insights")
            st.write(explanation)
