CREATE TABLE IF NOT EXISTS sync_jobs(
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    page_type_model TEXT,
    parser_model TEXT,
    status TEXT DEFAULT 'running',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT
);

CREATE TABLE IF NOT EXISTS sync_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_job_id TEXT REFERENCES sync_jobs(id),
    event_type TEXT,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_count INTEGER,
    data JSONB
);

CREATE TABLE IF NOT EXISTS pages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER REFERENCES documents(id),
  page_number INTEGER
);

CREATE TABLE IF NOT EXISTS page_type_predictions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER REFERENCES pages(id),
  model TEXT,
  predicted_page_type TEXT,
  model_usage JSON,
  timing JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page_parsed(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER REFERENCES pages(id),
  page_type TEXT,
  model TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  model_usage JSON,
  timing JSON,
  parsed_data JSON
);


create table if not exists schedule_a_itemizations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_parsed_id INTEGER REFERENCES page_parsed(id),
  date_received DATE,
  full_name TEXT,
  city TEXT,
  state TEXT,
  zipcode TEXT,
  contributor_code TEXT,
  occupation TEXT,
  employer TEXT,
  amount_this_period REAL,
  amount_cumulative_calendar_year REAL,
  amount_per_election_code TEXT,
  amount_per_election REAL
);

create table if not exists summary_pages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_parsed_id INTEGER REFERENCES page_parsed(id),
  name_of_filer TEXT,
  cover_period_from DATE,
  cover_period_to DATE,
  id_number TEXT,
  line_1_a_monetary_contributions REAL,
  line_1_b_monetary_contributions REAL,
  line_2_a_loans_received REAL,
  line_2_b_loans_received REAL,
  line_3_a_subtotal_cash_contributions REAL,
  line_3_b_subtotal_cash_contributions REAL,
  line_4_a_nonmonetary_contributions REAL,
  line_4_b_nonmonetary_contributions REAL,
  line_5_a_total_contributions REAL,
  line_5_b_total_contributions REAL,
  line_6_a_payments_made REAL,
  line_6_b_payments_made REAL,
  line_7_a_loans_made REAL,
  line_7_b_loans_made REAL,
  line_8_a_subtotal_cash_payments REAL,
  line_8_b_subtotal_cash_payments REAL,
  line_9_a_accrued_expenses REAL,
  line_9_b_accrued_expenses REAL,
  line_10_a_nonmonetary_adjustment REAL,
  line_10_b_nonmonetary_adjustment REAL,
  line_11_a_total_expenditures REAL,
  line_11_b_total_expenditures REAL,
  line_12_beginning_cash_balance REAL,
  line_13_cash_receipts REAL,
  line_14_misc_increase_cash REAL,
  line_15_cash_payments REAL,
  line_16_ending_cash_balance REAL,
  line_17_loan_guarantees_received REAL,
  line_18_cash_equivalents REAL,
  line_19_outstanding_debt REAL
);

create trigger if not exists trg_page_parsed_schedule_a_after_insert
  after insert on page_parsed
  for each row when new.page_type = 'schedule_a'
  begin
  insert into schedule_a_itemizations (
    page_parsed_id,
    date_received,
    full_name,
    city,
    state,
    zipcode,
    contributor_code,
    occupation,
    employer,
    amount_this_period,
    amount_cumulative_calendar_year,
    amount_per_election_code,
    amount_per_election
  )
  select 
    new.id,
    value->>'date_received',
    value->>'full_name',
    value->>'city',
    value->>'state',
    value->>'zipcode',
    value->>'contributor_code',
    value->>'occupation',
    value->>'employer',
    value->>'amount_this_period',
    value->>'amount_cumulative_calendar_year',
    value->>'amount_per_election_code',
    value->>'amount_per_election'
  from json_each(new.parsed_data->'line_items') as line_items;
  end;

create trigger if not exists trg_page_parsed_summary_after_insert
  after insert on page_parsed
  for each row when new.page_type = 'campaign_disclosure_summary_page'
  begin
  insert into summary_pages (
    page_parsed_id,
    name_of_filer,
    cover_period_from,
    cover_period_to,
    id_number,
    line_1_a_monetary_contributions,
    line_1_b_monetary_contributions,
    line_2_a_loans_received,
    line_2_b_loans_received,
    line_3_a_subtotal_cash_contributions,
    line_3_b_subtotal_cash_contributions,
    line_4_a_nonmonetary_contributions,
    line_4_b_nonmonetary_contributions,
    line_5_a_total_contributions,
    line_5_b_total_contributions,
    line_6_a_payments_made,
    line_6_b_payments_made,
    line_7_a_loans_made,
    line_7_b_loans_made,
    line_8_a_subtotal_cash_payments,
    line_8_b_subtotal_cash_payments,
    line_9_a_accrued_expenses,
    line_9_b_accrued_expenses,
    line_10_a_nonmonetary_adjustment,
    line_10_b_nonmonetary_adjustment,
    line_11_a_total_expenditures,
    line_11_b_total_expenditures,
    line_12_beginning_cash_balance,
    line_13_cash_receipts,
    line_14_misc_increase_cash,
    line_15_cash_payments,
    line_16_ending_cash_balance,
    line_17_loan_guarantees_received,
    line_18_cash_equivalents,
    line_19_outstanding_debt
  )
  values (
    new.id,
    new.parsed_data->>'name_of_filer',
    new.parsed_data->>'cover_period_from',
    new.parsed_data->>'cover_period_to',
    new.parsed_data->>'id_number',
    new.parsed_data->>'line_1_a_monetary_contributions',
    new.parsed_data->>'line_1_b_monetary_contributions',
    new.parsed_data->>'line_2_a_loans_received',
    new.parsed_data->>'line_2_b_loans_received',
    new.parsed_data->>'line_3_a_subtotal_cash_contributions',
    new.parsed_data->>'line_3_b_subtotal_cash_contributions',
    new.parsed_data->>'line_4_a_nonmonetary_contributions',
    new.parsed_data->>'line_4_b_nonmonetary_contributions',
    new.parsed_data->>'line_5_a_total_contributions',
    new.parsed_data->>'line_5_b_total_contributions',
    new.parsed_data->>'line_6_a_payments_made',
    new.parsed_data->>'line_6_b_payments_made',
    new.parsed_data->>'line_7_a_loans_made',
    new.parsed_data->>'line_7_b_loans_made',
    new.parsed_data->>'line_8_a_subtotal_cash_payments',
    new.parsed_data->>'line_8_b_subtotal_cash_payments',
    new.parsed_data->>'line_9_a_accrued_expenses',
    new.parsed_data->>'line_9_b_accrued_expenses',
    new.parsed_data->>'line_10_a_nonmonetary_adjustment',
    new.parsed_data->>'line_10_b_nonmonetary_adjustment',
    new.parsed_data->>'line_11_a_total_expenditures',
    new.parsed_data->>'line_11_b_total_expenditures',
    new.parsed_data->>'line_12_beginning_cash_balance',
    new.parsed_data->>'line_13_cash_receipts',
    new.parsed_data->>'line_14_misc_increase_cash',
    new.parsed_data->>'line_15_cash_payments',
    new.parsed_data->>'line_16_ending_cash_balance',
    new.parsed_data->>'line_17_loan_guarantees_received',
    new.parsed_data->>'line_18_cash_equivalents',
    new.parsed_data->>'line_19_outstanding_debt'
  );
  end;
