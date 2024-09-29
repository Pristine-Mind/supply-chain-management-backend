from transformers import (
    GPT2Tokenizer,
    GPT2LMHeadModel,
    Trainer,
    TrainingArguments,
    TextDataset,
    DataCollatorForLanguageModeling,
)


import pandas as pd

file_path_old = 'bid_data.csv'
data = pd.read_csv(file_path_old)

output_file = 'bid_suggestion_data.txt'

with open(output_file, 'w') as f:
    for _, row in data.iterrows():
        prompt = (
            f"Product ID: {row['product_id']}, Listed Price: {row['listed_price']}, "
            f"Current Bid: {row['current_bid']}, Number of Past Bids: {row['past_bids_count']}, "
            f"Time Since Listing: {row['time_since_listing']} days. "
            f"Suggested Bid: {row['suggested_bid']}\n"
        )
        f.write(prompt)

print(f"Data successfully converted to text format and saved at {output_file}")


tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
model = GPT2LMHeadModel.from_pretrained("gpt2")


def load_dataset(file_path, tokenizer):
    return TextDataset(
        tokenizer=tokenizer,
        file_path=file_path,
        block_size=128
    )


def get_data_collator(tokenizer):
    return DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )


file_path = "bid_suggestion_data.txt"
train_dataset = load_dataset(file_path, tokenizer)
data_collator = get_data_collator(tokenizer)

training_args = TrainingArguments(
    output_dir="./gpt2-bid-finetuned",
    overwrite_output_dir=True,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    save_steps=10_000,
    save_total_limit=2,
)

trainer = Trainer(
    model=model,
    args=training_args,
    data_collator=data_collator,
    train_dataset=train_dataset,
)

trainer.train()

model.save_pretrained("./gpt2-bid-finetuned")
tokenizer.save_pretrained("./gpt2-bid-finetuned")
