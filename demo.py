import gradio as gr
import numpy as np
import onnxruntime as ort
from PIL import Image
from segment_anything.onnxpredictor import SamOnnxPredictor
import cv2
import logging
import hashlib
from pathlib import Path
import os

logging.basicConfig(level=logging.INFO)
# Path to your ONNX model
VIT_PATH = "./models/vit_quantized.onnx"
MASK_PATH = "./models/sam_vit_h.onnx"

# Load the ONNX model
# vit_session = ort.InferenceSession(VIT_PATH)
mask_session = ort.InferenceSession(MASK_PATH)
predictor = SamOnnxPredictor(VIT_PATH)
# image_embedding = gr.State(None)
image_homepath = None

def load_image(image: Image.Image) -> np.array:
    """
    Perform segmentation using the ONNX model.
    """
    # image = np.array(image)
    hash = hashlib.md5(image.tobytes()).hexdigest()
    image_cvt = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    logging.debug(f"type of image: {type(image_cvt)}")
    predictor.set_image(image_cvt)
    embed = predictor.get_image_embedding()[0]
    np.save(image_homepath / f"{hash}.npy", embed)
    return embed
    

def segment_image(image_path: str, coord: tuple[int, int]):
    """
    Perform segmentation using the ONNX model.
    """

    image = cv2.imread(image_path)
    hash = hashlib.md5(image).hexdigest()
    global image_homepath
    image_homepath = Path(image_path).parent
    embed_path = image_homepath / f"{hash}.npy"
    if os.path.exists(embed_path):
        image_embedding = np.load(embed_path)
    else:
        image_embedding = load_image(image)
    logging.debug(f"image embedding: {image_embedding}")

    input_point = np.array([coord])
    # input_point = np.array([[500, 450]])
    input_label = np.array([1])
    
    onnx_coord = np.concatenate([input_point, np.array([[0.0, 0.0]])], axis=0)[None, :, :]
    onnx_label = np.concatenate([input_label, np.array([-1])], axis=0)[None, :].astype(np.float32)

    onnx_coord = predictor.transform.apply_coords(onnx_coord, image.shape[:2]).astype(np.float32)

    onnx_mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
    onnx_has_mask_input = np.zeros(1, dtype=np.float32)
    
    
    ort_inputs = {
    "image_embeddings": image_embedding,
    "point_coords": onnx_coord,
    "point_labels": onnx_label,
    "mask_input": onnx_mask_input,
    "has_mask_input": onnx_has_mask_input,
    "orig_im_size": np.array(image.shape[:2], dtype=np.float32)
    }
    
    masks, _, low_res_logits = mask_session.run(None, ort_inputs)
    masks = masks > predictor.model.mask_threshold
    mask = masks[:,0,:,:]
    
    mask_image = draw_mask(mask)
    # logging.info(f"image shape: {image.shape}\n mask shape: {mask_image.shape}")
    # output_img = cv2.addWeighted(image, alpha, mask_image, beta, 0.0)
    image_cvt = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    output_img = Image.alpha_composite(
        Image.fromarray(image_cvt.astype('uint8')).convert("RGBA"),
        Image.fromarray((mask_image * 255).astype('uint8'), mode="RGBA"))
    # logging.info(mask_image)
    return output_img

def get_select_coords(img, evt: gr.SelectData):
    return segment_image(img, (evt.index[0], evt.index[1]))

def draw_mask(mask):
    color = np.array([30/255, 144/255, 255/255, 0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    return mask_image


with gr.Blocks() as demo:
    with gr.Row():
        input_img = gr.Image(type="filepath")
        output_img = gr.Image(type="pil")
        input_img.select(get_select_coords, [input_img], [output_img])


if __name__ == "__main__":
    demo.title = "Segment Anything ONNX Demo"
    demo.launch()
