import json
import io
import random
import time

import pandas
import openai

from pkg.config import config
from pkg.storage import storage


DAYS_COUNT = 15

samconfig_file = config.SAMConfig('samconfig.toml')

storage_client = storage.Client(
    s3_data_bucket_name=samconfig_file.get_parameter('S3DataBucketName'),
)

equities_bars_file_names = storage_client.list_file_names(
    prefix=storage.PREFIX_EQUITY_BARS_PROCESSED_PATH
)

dataframes = storage_client.load_dataframes(
    prefix=storage.PREFIX_EQUITY_BARS_PROCESSED_PATH,
    file_names=equities_bars_file_names,
)

dataframe = pandas.concat(dataframes)

grouped_dataframe = dataframe.groupby('ticker')

jsonl_data: list[dict[str, str]] = []
for group_name in grouped_dataframe.groups.keys():
    group = grouped_dataframe.get_group(group_name)

    sorted_group = group.sort_values(
        by='timestamp',
        ascending=False,
    )

    oldest_timestamp = sorted_group['timestamp'].min()
    newest_timestamp = sorted_group['timestamp'].max()

    difference = (newest_timestamp - oldest_timestamp).days

    # arbitrary minimum number of days to account for weekends and holidays
    if difference < DAYS_COUNT:
        continue

    oldest_unix = oldest_timestamp.timestamp()
    newest_unix = newest_timestamp.timestamp()

    for i in range(0, 3):
        random_unix = random.uniform(oldest_unix, newest_unix)

        start_timestamp = pandas.Timestamp.fromtimestamp(random_unix)
        end_timestamp = start_timestamp + pandas.Timedelta(days=DAYS_COUNT)

        if end_timestamp > newest_timestamp:
            end_timestamp = newest_timestamp
            start_timestamp = end_timestamp - pandas.Timedelta(days=DAYS_COUNT)

        selected_rows = sorted_group[
            (sorted_group['timestamp'] >= start_timestamp) &
            (sorted_group['timestamp'] <= end_timestamp)
        ]

        selected_rows.reset_index(
            inplace=True,
            drop=True,
        )

        close_prices = selected_rows['close_price']
        price_changes = close_prices.diff().tolist()
        # remove the first value which is NaN
        price_changes = price_changes[1:]
        price_changes.append(0.0)
        price_changes = [round(float(change), 2) for change in price_changes]

        completions: list[str] = []
        for index, row in selected_rows.iloc[:5].iterrows():
            price_change = price_changes[index]

            if price_change > 0.0:
                completions.append('up')
            elif price_change < 0.0:
                completions.append('down')
            else:
                completions.append('flat')

        prompts: list[str] = []
        for index, row in selected_rows.iloc[5:].iterrows():
            prompt = 'timestamp: {}, ticker: {}, open_price: {:.2f}, high_price: {:.2f}, low_price: {:.2f}, close_price: {:.2f}, volume: {:.2f}'.format(
                row['timestamp'],
                row['ticker'],
                row['open_price'],
                row['high_price'],
                row['low_price'],
                row['close_price'],
                row['volume'],
            )

            prompts.append(prompt)

        jsonl_data.append({
            'prompt': ', '.join(prompts) + ' -> ',
            'completion': ' ' + ', '.join(completions) + '\n',
        })

jsonl_file = io.StringIO()
for jsonl_line in jsonl_data:
    json.dump(jsonl_line, jsonl_file)
    jsonl_file.write('\n')

openai.api_key = samconfig_file.get_parameter('OpenAIAPIKey')

openai_file_response = openai.File.create(
    file=bytes(jsonl_file.getvalue().rstrip('\n'), encoding='utf-8'),
    purpose='fine-tune',
)

file_id = openai_file_response['id']

openai_fine_tune_create_response = openai.FineTune.create(
    training_file=file_id,
    model='ada',
)

fine_tune_id = openai_fine_tune_create_response['id']

model_id = None
while model_id is None:
    openai_fine_tune_list_response = openai.FineTune.list_events(fine_tune_id)

    for event in openai_fine_tune_list_response['data']:
        message = event['message']
        if 'Uploaded model' in message:
            model_id = message.split(': ')[1]
            break

    time.sleep(10)

print(model_id)
