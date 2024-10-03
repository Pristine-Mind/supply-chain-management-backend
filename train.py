import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn
import torch.optim as optim

# Load sequences
data = pd.read_csv('bid_sequences.csv').values


class BidDataset(Dataset):
    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        sequence = torch.tensor(self.data[idx, :-1], dtype=torch.float32)
        target = torch.tensor(self.data[idx, -1], dtype=torch.float32)
        return sequence, target


# Create dataset and dataloader
dataset = BidDataset(data)
dataloader = DataLoader(dataset, batch_size=32, shuffle=True)


class TransformerBidPredictor(nn.Module):
    def __init__(self, input_dim, d_model, num_heads, num_layers, dropout=0.1):
        super(TransformerBidPredictor, self).__init__()
        self.embedding = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=num_heads, dropout=dropout)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc_out = nn.Linear(d_model, 1)

    def forward(self, x):
        x = self.embedding(x.unsqueeze(-1))
        x = self.transformer_encoder(x)
        x = self.fc_out(x[-1])
        return x


# Initialize model
input_dim = 1
d_model = 32
num_heads = 4
num_layers = 2
model = TransformerBidPredictor(input_dim, d_model, num_heads, num_layers)

criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

# Training loop
epochs = 10
for epoch in range(epochs):
    model.train()
    for sequences, targets in dataloader:
        optimizer.zero_grad()
        outputs = model(sequences)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()
    print(f"Epoch {epoch+1}/{epochs}, Loss: {loss.item()}")

# Save the trained model
torch.save(model.state_dict(), 'transformer_bid_model.pth')
