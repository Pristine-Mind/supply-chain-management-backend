from transformers import GPT2LMHeadModel, GPT2Tokenizer

model = GPT2LMHeadModel.from_pretrained("./gpt2-bid-finetuned")
tokenizer = GPT2Tokenizer.from_pretrained("./gpt2-bid-finetuned")


def get_local_llm_price_suggestion(product_name, category, listed_price, current_bid, past_bids_count, time_since_listing):
    prompt = (
        f"Product Name: {product_name}, Category: {category}, Listed Price: {listed_price}, "
        f"Current Highest Bid: {current_bid}, Number of Bids: {past_bids_count}, Time Since Listing: {time_since_listing} days. "
        f"Suggested Bid: "
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    output = model.generate(**inputs, max_length=50, num_return_sequences=1, temperature=0.7)

    suggested_price = tokenizer.decode(output[0], skip_special_tokens=True).split("Suggested Bid:")[-1].strip()
    try:
        suggested_price = float(suggested_price)
    except ValueError:
        suggested_price = listed_price * 1.05

    return round(suggested_price, 2)
