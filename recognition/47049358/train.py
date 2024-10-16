"""
containing the source code for training, validating, testing and saving your model. The model
should be imported from “modules.py” and the data loader should be imported from “dataset.py”. Make
sure to plot the losses and metrics during training
"""

from dataset import X_train, y_train, Prostate3dDataset
from modules import ImprovedUnet
import matplotlib.pyplot as plt
import torch
from torch.utils.data import DataLoader
import torch.nn as nn
from time import time
from tqdm import tqdm
import math


NUM_EPOCHS = 300
BATCH_SIZE = 2
LEARNING_RATE = 5e-4
WEIGHT_DECAY = 1e-5
LR_INITIAL = 0.985
LOSS_IDX = 3

class BaseDice(nn.Module):
    def __init__(self, epsilon = 1e-7):
        super(BaseDice, self).__init__()
        self.epsilon = epsilon

    def forward(self, y_true, y_pred):
        raise NotImplementedError("Sublasses should implement this method.")

class ExponentialWeightedLoss(BaseDice):
    def __init__(self, epsilon=1e-7):
        super().__init__(epsilon)

    def __str__(self):
        return 'ExponentialWeightedLoss'

    def forward(self, y_true, y_pred):

        num_masks = y_true.size(-1)
        d_coefs = torch.zeros(num_masks, device=y_true.device)
        for i in range(num_masks):
            ground_truth_seg = y_true[:, :, :, :, i]
            pred_seg = y_pred[:, :, :, :, i]

            d_coef = (2 * torch.sum(torch.mul(ground_truth_seg, pred_seg))) / (torch.sum(ground_truth_seg + pred_seg) + self.epsilon)
            d_coefs[i] = d_coef

        weighted, _ = torch.sort(d_coefs)

        for i in range(num_masks):
            weighted[i] = d_coefs[i] / (math.e ** i)
        
        overall_loss = 1 - (1 / num_masks) * torch.sum(d_coefs)
        weighted_loss = 1 - (1 / num_masks) * torch.sum(weighted)
        return overall_loss, d_coefs, weighted_loss
    
class ArithmeticWeightedLoss(BaseDice):
    def __init__(self, epsilon=1e-7):
        super().__init__(epsilon)

    def __str__(self):
        return 'ArithmeticWeightedLoss'

    def forward(self, y_true, y_pred):

        num_masks = y_true.size(-1)
        d_coefs = torch.zeros(num_masks, device=y_true.device)
        for i in range(num_masks):
            ground_truth_seg = y_true[:, :, :, :, i]
            pred_seg = y_pred[:, :, :, :, i]

            d_coef = (2 * torch.sum(torch.mul(ground_truth_seg, pred_seg))) / (torch.sum(ground_truth_seg + pred_seg) + self.epsilon)
            d_coefs[i] = d_coef

        weighted, _ = torch.sort(d_coefs)

        for i in range(num_masks):
            weighted[i] = d_coefs[i] / (i + 1)
        
        overall_loss = 1 - (1 / num_masks) * torch.sum(d_coefs)
        weighted_loss = 1 - (1 / num_masks) * torch.sum(weighted)
        return overall_loss, d_coefs, weighted_loss
    
class PaperLoss(BaseDice):
    def __init__(self, epsilon=1e-7):
        super().__init__(epsilon)

    def __str__(self):
        return 'PaperLoss'

    def forward(self, y_true, y_pred):

        num_masks = y_true.size(-1)
        d_coefs = torch.zeros(num_masks, device=y_true.device)
        for i in range(num_masks):
            ground_truth_seg = y_true[:, :, :, :, i]
            pred_seg = y_pred[:, :, :, :, i]

            d_coef = (2 * torch.sum(torch.mul(ground_truth_seg, pred_seg))) / (torch.sum(ground_truth_seg + pred_seg) + self.epsilon)
            d_coefs[i] = d_coef

        overall_loss = (- 1 / num_masks) * torch.sum(d_coefs)
        return overall_loss, d_coefs, None
    
class AlternativeLoss(BaseDice):
    def __init__(self, epsilon=1e-7):
        super().__init__(epsilon)

    def __str__(self):
        return 'AlternativeLoss'

    def forward(self, y_true, y_pred):

        num_masks = y_true.size(-1)
        d_coefs = torch.zeros(num_masks, device=y_true.device)
        for i in range(num_masks):
            ground_truth_seg = y_true[:, :, :, :, i]
            pred_seg = y_pred[:, :, :, :, i]

            d_coef = (2 * torch.sum(torch.mul(ground_truth_seg, pred_seg))) / (torch.sum(ground_truth_seg + pred_seg) + self.epsilon)
            d_coefs[i] = d_coef

        overall_loss = 1 - (1 / num_masks) * torch.sum(d_coefs)
        return overall_loss, d_coefs, None

def train(model, train_set, loss, num_epochs=NUM_EPOCHS, device="cuda"):

    # set up criterion, optimiser, and scheduler for learning rate. 
    criterion = loss
    optimiser = torch.optim.Adam(model.parameters(), lr = LEARNING_RATE, weight_decay = WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ExponentialLR(optimiser, gamma = LR_INITIAL)

    model.to(device)
    model.train()

    training_losses = []
    
    train_loader = DataLoader(dataset = train_set, batch_size = BATCH_SIZE)

    for epoch in range(num_epochs):
        running_loss = 0.0
        segment_coefs = None
        for inputs, masks in tqdm(train_loader):

            inputs, masks = inputs.to(device), masks.to(device)
            optimiser.zero_grad()
            outputs = model(inputs)

            # the weighted value is only used for updating gradients!
            loss, d_coefs, weighted = criterion(y_true = masks, y_pred = outputs) 

            if segment_coefs == None:
                segment_coefs = d_coefs
            else:
                segment_coefs += d_coefs

            if weighted == None:
                loss.backward()
            else:
                weighted.backward()

            optimiser.step()

            running_loss += loss.item()

        scheduler.step()

        for i in range(len(segment_coefs)):
            print(f"Epoch {epoch + 1} Segment {i} - Training Dice Coefficient: {segment_coefs[i] / len(train_loader)}")

        print(f"Epoch {epoch + 1}, Training Loss: {running_loss / len(train_loader)}")

    return model, training_losses

# connect to gpu
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if not torch.cuda.is_available():
    print("Warning CUDA not Found. Using CPU")

# create model. 
model = ImprovedUnet()

# Importing Dataloader breaks the implementation. Hence they are loaded below instead:

train_set = Prostate3dDataset(X_train, y_train)

loss_map = {0 : PaperLoss(), 1 : AlternativeLoss(), 2 : ExponentialWeightedLoss(), 3 : ArithmeticWeightedLoss()}

loss = loss_map.get(LOSS_IDX)

print("> Start Training")

start = time()

# train improved unet
trained_model, training_losses = train(model, train_set, loss = loss,
                                                            device=device, num_epochs=NUM_EPOCHS)

end = time()

elapsed_time = end - start
print(f"Training completed in {elapsed_time:.2f} seconds")

training_losses = []

plt.figure(figsize=(10,5))
plt.plot(training_losses, label='Training Loss')
plt.title('Losses over epochs')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()
plt.grid(True)
plt.savefig(f'unet_training_losses_over_epochs_{str(loss)}.png')
plt.close()