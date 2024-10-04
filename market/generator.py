import re

from transformers import GPT2LMHeadModel, GPT2Tokenizer

model = GPT2LMHeadModel.from_pretrained("./gpt2-bid-finetuned")
tokenizer = GPT2Tokenizer.from_pretrained("./gpt2-bid-finetuned")


def get_local_llm_price_suggestion(product_name, category, listed_price, current_bid, past_bids_count, time_since_listing):
    prompt = (
        f"The highest bid so far is {current_bid}. Suggest a single new bid amount that is higher than {current_bid}. Provide only the number:"
    )

    print(prompt, "Prompt for the model")

    inputs = tokenizer(prompt, return_tensors="pt")
    output = model.generate(
        **inputs,
        max_new_tokens=50,
        temperature=0.7,
        do_sample=True,
        top_p=0.9,
        top_k=50
    )

    generated_text = tokenizer.decode(output[0], skip_special_tokens=True)
    print(generated_text, "Full generated text from the model")

    potential_numbers = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', generated_text)
    print(potential_numbers, "Potential numbers extracted from the generated text")

    if potential_numbers:
        suggested_price = float(potential_numbers[0].replace(',', ''))
    else:
        suggested_price = current_bid * 1.05

    if suggested_price <= current_bid:
        suggested_price = current_bid * 1.05

    return round(suggested_price, 2)
