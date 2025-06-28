import llm

from commonplace import logger


def get_model(model_name: str) -> llm.Model:
    """Get the configured LLM model, with helpful help."""
    try:
        return llm.get_model(model_name)

    except Exception as e:
        logger.error(f"Failed to load model '{model_name}': {e}")
        logger.info(f"Pick: {llm.get_models()}")
        logger.info("Make sure the model is installed and configured. Try: llm models list")
        raise
