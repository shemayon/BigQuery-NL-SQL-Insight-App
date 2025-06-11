import os
import logging
from google.cloud import bigquery
from google.oauth2 import service_account



logger = logging.getLogger('mcp_bigquery_streamlit')
handler_stdout = logging.StreamHandler()

log_filename = 'mcp_bigquery_streamlit.log'
log_path     = os.path.join(os.getcwd(), log_filename)
handler_file = logging.FileHandler(log_path)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler_stdout.setFormatter(formatter)
handler_file.setFormatter(formatter)
logger.addHandler(handler_stdout)
logger.addHandler(handler_file)
logger.setLevel(logging.DEBUG)
logger.info(f"Starting Streamlit BigQuery App with MCP integration, logs at {log_path}")

# ——— BigQueryDatabase Class ———
class BigQueryDatabase:
    def __init__(self, project: str, location: str, key_file: str | None, datasets_filter: list[str]):
        logger.info(f"Initializing BigQueryDatabase: project={project}, location={location}, key_file={key_file}")
        if not project:
            raise ValueError("Project is required")
        if not location:
            raise ValueError("Location is required")
        credentials = None
        if key_file:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    key_file,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except Exception as e:
                logger.error(f"Error loading credentials: {e}")
                raise
        self.client = bigquery.Client(credentials=credentials, project=project, location=location)
        self.datasets_filter = datasets_filter

    def execute_query(self, query: str, params: dict[str, any] | None = None) -> list[dict[str, any]]:
        logger.debug(f"Executing query: {query}")
        try:
            if params:
                job = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params))
            else:
                job = self.client.query(query)
            results = job.result()
            rows = [dict(row.items()) for row in results]
            logger.debug(f"Query returned {len(rows)} rows")
            return rows
        except Exception as e:
            logger.error(f"Query error: {e}")
            raise

    def list_tables(self) -> list[str]:
        logger.debug("Listing tables")
        tables = []
        for ds in (self.datasets_filter or [None]):
            if ds:
                dataset_ref = f"{self.client.project}.{ds}"
                for table in self.client.list_tables(dataset_ref):
                    tables.append(f"{dataset_ref}.{table.table_id}")
        logger.debug(f"Found tables: {tables}")
        return tables

    def describe_table(self, table_name: str) -> list[dict[str, any]]:
        logger.debug(f"Describing table: {table_name}")
        parts = table_name.split('.')
        dataset = parts[-2]
        table = parts[-1]
        query = f"""
            SELECT ddl
            FROM `{self.client.project}.{dataset}.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = @table_name;
        """
        return self.execute_query(query, params={"table_name": table})


