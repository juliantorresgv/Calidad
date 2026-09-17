"""
Fine-tuning de embeddings con datos de Integr@.
Ejecutar: python finetune_embeddings.py
"""
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import json

# Cargar modelo base
model = SentenceTransformer("intfloat/multilingual-e5-large")

# Cargar dataset
with open(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\finetune_dataset.json", encoding="utf-8") as f:
    pairs = json.load(f)

# Crear ejemplos de entrenamiento
train_examples = []
for pair in pairs:
    if pair["negative"]:
        train_examples.append(InputExample(
            texts=[pair["query"], pair["positive"], pair["negative"]]
        ))

print(f"Total ejemplos: {len(train_examples)}")

# DataLoader
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.TripletLoss(model=model)

# Fine-tune
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    output_path=r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\embeddings_finetuned",
    show_progress_bar=True,
)

print(f"Modelo guardado en: C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\embeddings_finetuned")
