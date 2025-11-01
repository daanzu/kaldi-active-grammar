# Kaldi Active Grammar - Agent Information

This document provides technical architectural information for AI coding agents (or humans!) working with the kaldi-active-grammar project.

WARNING: This file may be auto-generated and/or out of date!

## Project Overview

**Kaldi Active Grammar** is a Python package that enables context-based command and control using the Kaldi automatic speech recognition engine with dynamically manageable grammars.

### Key Technologies

- **Speech Recognition**: Kaldi ASR engine
- **Language**: Python 3.6+
- **Supported Platforms**: Windows, Linux, macOS (64-bit)
- **Primary Integration**: Dragonfly speech recognition framework
- **Model Architecture**: Kaldi nnet3 chain models

### Version Information

- **Current Version**: See [`kaldi_active_grammar/__init__.py:8`](kaldi_active_grammar/__init__.py:8)
- **Required Model Version**: See [`kaldi_active_grammar/__init__.py:10`](kaldi_active_grammar/__init__.py:10)
- **Version History**: See [`CHANGELOG.md`](CHANGELOG.md:1)

## Core Modules

### Compiler (`kaldi_active_grammar/compiler.py`)

The **Compiler** module is responsible for compiling grammar rules into FST (Finite State Transducer) format for use by the Kaldi decoder.

**Key Classes:**
- `Compiler`: Main compilation engine that manages grammar compilation and FST generation
- `KaldiRule`: Represents an individual grammar rule with associated FST representation

**Responsibilities:**
- Grammar-to-FST compilation
- Rule caching and management
- Dynamic grammar loading/unloading
- Lexicon handling and pronunciation generation

### Model (`kaldi_active_grammar/model.py`)

The **Model** module manages the Kaldi acoustic model and lexicon operations.

**Key Classes:**
- `Lexicon`: Manages phoneme sets and phoneme conversion (CMU to XSAMPA)
- `Model`: Orchestrates the acoustic model and lexicon

**Responsibilities:**
- Loading and validating Kaldi nnet3 chain models
- Lexicon management (CMU, XSAMPA phoneme sets)
- Word pronunciation generation (local via g2p_en or online)
- Model version verification

### Wrapper (`kaldi_active_grammar/wrapper.py`)

The **Wrapper** module provides the FFI (Foreign Function Interface) to native Kaldi binaries.

**Key Classes:**
- `KaldiAgfNNet3Decoder`: Main decoder for active grammar FSTs
- `KaldiLafNNet3Decoder`: Alternative LAF (Linear Alignment Filter) decoder
- `KaldiPlainNNet3Decoder`: Decoder for plain dictation

**Responsibilities:**
- Native library binding
- Audio decoding
- Hypothesis generation and lattice manipulation

### WFST (Weighted Finite State Transducer) (`kaldi_active_grammar/wfst.py`)

The **WFST** module handles FST representation and manipulation.

**Key Classes:**
- `WFST`: Python-based FST implementation
- `NativeWFST`: Native (C++-based) FST wrapper
- `SymbolTable`: Maps symbols to numeric IDs for FST operations

**Responsibilities:**
- FST construction and modification
- Symbol table management
- FST serialization and caching

### Plain Dictation (`kaldi_active_grammar/plain_dictation.py`)

The **PlainDictationRecognizer** module provides simple dictation recognition without grammar rules.

**Features:**
- Works with standard Kaldi HCLG.fst files
- Fallback option for dictation-only use cases
- Compatible with both pre-trained models and custom models

### Utilities (`kaldi_active_grammar/utils.py`)

Utility functions for:
- File discovery and path handling
- Symbol table loading
- External process management
- Cross-platform compatibility

## Architecture Overview

```
┌─────────────────────────────────────────┐
│     Dragonfly / User Application        │
└────────────────┬────────────────────────┘
                 │
┌─────────────────▼────────────────────────┐
│  Compiler (Grammar Rules → FSTs)         │
├──────────────────────────────────────────┤
│ • Grammar compilation                    │
│ • FST generation & caching               │
│ • Rule management                        │
└────────────────┬────────────────────────┘
                 │
┌─────────────────▼────────────────────────┐
│  Model (Acoustic Model + Lexicon)        │
├──────────────────────────────────────────┤
│ • Kaldi nnet3 chain model loading        │
│ • Pronunciation generation               │
│ • Lexicon management                     │
└────────────────┬────────────────────────┘
                 │
┌─────────────────▼────────────────────────┐
│  Wrapper (FFI to Native Kaldi)           │
├──────────────────────────────────────────┤
│ • KaldiAgfNNet3Decoder                   │
│ • KaldiLafNNet3Decoder                   │
│ • Audio decoding & lattice generation    │
└────────────────┬────────────────────────┘
                 │
┌─────────────────▼────────────────────────┐
│  Native Kaldi Binaries (C++)             │
├──────────────────────────────────────────┤
│ • Acoustic model decoding                │
│ • FST operations                         │
│ • Lattice operations                     │
└──────────────────────────────────────────┘
```

## Key Features & Capabilities

### Dynamic Grammar Management
- Grammars can be marked active/inactive on a per-utterance basis
- Enables context-aware command recognition
- Improves accuracy by reducing possible recognitions

### Grammar Compilation
- Multiple independent grammars with nonterminals
- Separate compilation and dynamic stitching at decode-time
- Shared dictation grammar between command grammars

### Performance & Accuracy
- Context-based activation reduces vocabulary scope
- Efficient FST-based representation
- Support for weighted grammar rules

### Dictation Support
- Integrated dictation grammar
- Plain dictation interface (HCLG.fst compatible)
- Pronunciation generation via g2p_en or online service

## Development Integration

### Testing
- Test suite in `tests/` directory
- Pytest configuration in `pyproject.toml`
- Coverage reporting can be enabled
- Integration tests for grammar compilation and decoding
- Run tests with `just test`
- To setup virtual environment for tests: `uv venv && uv pip install -r requirements-test.txt -r requirements-editable.txt`

### Examples
- `examples/plain_dictation.py`: Plain dictation usage
- `examples/mix_dictation.py`: Mixed command+dictation
- `examples/full_example.py`: Comprehensive example
- `examples/audio.py`: Audio handling utilities

### Build System
- CMake-based native compilation
- Scikit-build integration for wheel generation
- Multi-platform support (Windows/Linux/macOS)
- GitHub Actions CI/CD pipeline

## System Requirements

- **Python**: 3.6+, 64-bit
- **RAM**: 1GB+ (model + grammars)
- **Disk Space**: 1GB+ (model + temporary files)
- **Model Type**: Kaldi left-biphone nnet3 chain (specific modifications required)
- **Audio Input**: Microphone or audio file

## Workflow

1. **Model Initialization**: Load Kaldi nnet3 chain model
2. **Grammar Definition**: Define command/rule grammar
3. **Compilation**: Compiler converts grammar rules to FSTs
4. **Activation**: Set which grammars are active for current utterance
5. **Decoding**: Wrapper processes audio through Kaldi decoder
6. **Recognition**: Return recognized utterance and associated action
