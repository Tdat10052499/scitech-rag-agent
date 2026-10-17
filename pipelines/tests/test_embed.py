import hashlib
import json
from pathlib import Path

import pytest

from scitech_pipelines import cli, embed
from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.cli import build_parser, main
from scitech_pipelines.embed import EMBED_MANIFEST, EMBED_STATE, embed_chunks

duckdb = pytest.importorskip("duckdb")
np = pytest.importorskip("numpy")
pytest.importorskip("pyarrow")
jsonschema = pytest.importorskip("jsonschema")

from test_chunk import SCHEMA, fixture_documents, write_documents  # noqa: E402

DIM = 8


class FakeEncoder:
    """Deterministic vectors from a hash of the text, L2-normalised like the real encoder."""

    def __init__(self, name: str = "fake/model-a", dimension: int = DIM, fail_after: int = -1):
        self.name = name
        self.dimension = dimension
        self.calls: list[list[str]] = []
        self.fail_after = fail_after

    def encode(self, texts):
        if len(self.calls) == self.fail_after:
            raise RuntimeError("GPU lost")
        self.calls.append(list(texts))
        return np.stack([vector(t, self.dimension) for t in texts])

    def info(self):
        return {"device": "cpu", "batch_size": 2}


def vector(text: str, dimension: int = DIM):
    raw = np.frombuffer(hashlib.sha256(text.encode()).digest()[: dimension * 4], np.uint32)
    v = raw.astype(np.float64) - 2**31
    return (v / np.linalg.norm(v)).astype(np.float32)


@pytest.fixture
def chunks(tmp_path: Path) -> Path:
    docs = write_documents(tmp_path / "data" / "processed" / "documents", fixture_documents())
    out = tmp_path / "data" / "processed" / "chunks"
    chunk_documents(docs, out, log=lambda _: None)
    return out


def read_vectors(out: Path) -> dict[str, tuple[list[float], str]]:
    con = duckdb.connect()
    rows = con.execute(
        "SELECT chunk_id, embedding, embedding_model "
        f"FROM read_parquet('{(out / 'part-*.parquet').as_posix()}')"
    ).fetchall()
    con.close()
    return {chunk_id: (emb, model) for chunk_id, emb, model in rows}


def chunk_texts(chunks: Path) -> dict[str, str]:
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT chunk_id, text FROM read_parquet('{(chunks / 'chunks.parquet').as_posix()}')"
    ).fetchall()
    con.close()
    return dict(rows)


def test_every_chunk_gets_its_vector(chunks: Path, tmp_path: Path):
    out = tmp_path / "emb"
    manifest = embed_chunks(chunks, out, FakeEncoder(), part_size=6, log=lambda _: None)
    texts = chunk_texts(chunks)
    vectors = read_vectors(out)
    assert set(vectors) == set(texts)
    for chunk_id, (emb, model) in vectors.items():
        assert model == "fake/model-a"
        assert np.allclose(emb, vector(texts[chunk_id]))
        assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-6)
    assert sorted(p.name for p in out.glob("part-*.parquet")) == [
        f"part-{i:05d}.parquet" for i in range(4)
    ]
    assert manifest["model"] == "fake/model-a"
    assert manifest["dimension"] == DIM
    assert manifest["counts"] == {
        "chunks": 20,
        "parts": 4,
        "parts_resumed": 0,
        "chunks_embedded_this_run": 20,
    }
    assert manifest["machine"]["device"] == "cpu"
    assert json.loads((out / EMBED_MANIFEST).read_text(encoding="utf-8")) == manifest


def test_chunk_with_model_name_matches_contract(chunks: Path, tmp_path: Path):
    """What `load` will store: the chunk fields plus `embedding_model` from this step."""
    out = tmp_path / "emb"
    embed_chunks(chunks, out, FakeEncoder(), log=lambda _: None)
    con = duckdb.connect()
    result = con.execute(
        f"SELECT c.*, e.embedding_model FROM "
        f"read_parquet('{(chunks / 'chunks.parquet').as_posix()}') c JOIN "
        f"read_parquet('{(out / 'part-*.parquet').as_posix()}') e USING (chunk_id)"
    )
    names = [d[0] for d in result.description]
    records = [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    con.close()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert len(records) == 20
    for r in records:
        record = {k: v for k, v in r.items() if v is not None}
        assert [e.message for e in validator.iter_errors(record)] == [], r["chunk_id"]


def test_interrupted_run_resumes_at_the_missing_part(chunks: Path, tmp_path: Path):
    out = tmp_path / "emb"
    with pytest.raises(RuntimeError, match="GPU lost"):
        embed_chunks(chunks, out, FakeEncoder(fail_after=2), part_size=6, log=lambda _: None)
    assert len(list(out.glob("part-*.parquet"))) == 2
    assert not (out / EMBED_MANIFEST).exists()
    encoder = FakeEncoder()
    manifest = embed_chunks(chunks, out, encoder, part_size=6, log=lambda _: None)
    assert [len(c) for c in encoder.calls] == [6, 2]
    assert manifest["counts"]["parts_resumed"] == 2
    assert manifest["counts"]["chunks_embedded_this_run"] == 8
    assert len(read_vectors(out)) == 20


def test_complete_output_is_skipped_and_a_deleted_part_redone(chunks: Path, tmp_path: Path):
    out = tmp_path / "emb"
    first = embed_chunks(chunks, out, FakeEncoder(), part_size=6, log=lambda _: None)
    encoder = FakeEncoder()
    assert embed_chunks(chunks, out, encoder, part_size=6, log=lambda _: None) == first
    assert encoder.calls == []
    (out / "part-00001.parquet").unlink()
    embed_chunks(chunks, out, encoder, part_size=6, log=lambda _: None)
    assert [len(c) for c in encoder.calls] == [6]
    assert len(read_vectors(out)) == 20


def test_other_settings_do_not_mix_with_existing_vectors(chunks: Path, tmp_path: Path):
    out = tmp_path / "emb"
    embed_chunks(chunks, out, FakeEncoder(), part_size=6, log=lambda _: None)
    for encoder, kwargs in [
        (FakeEncoder("fake/model-b"), {"part_size": 6}),
        (FakeEncoder(), {"part_size": 5}),
        (FakeEncoder(), {"part_size": 6, "passage_prefix": "passage: "}),
    ]:
        with pytest.raises(ValueError, match="other settings"):
            embed_chunks(chunks, out, encoder, log=lambda _: None, **kwargs)
    manifest = embed_chunks(
        chunks, out, FakeEncoder("fake/model-b"), part_size=6, force=True, log=lambda _: None
    )
    assert manifest["model"] == "fake/model-b"
    assert {model for _, model in read_vectors(out).values()} == {"fake/model-b"}
    state = json.loads((out / EMBED_STATE).read_text(encoding="utf-8"))
    assert state["model"] == "fake/model-b"


def test_rechunked_input_is_detected(chunks: Path, tmp_path: Path):
    out = tmp_path / "emb"
    embed_chunks(chunks, out, FakeEncoder(), log=lambda _: None)
    docs = chunks.parent / "documents"
    chunk_documents(docs, chunks, max_words=80, overlap_words=10, log=lambda _: None)
    with pytest.raises(ValueError, match="other chunks"):
        embed_chunks(chunks, out, FakeEncoder(), log=lambda _: None)


def test_prefix_and_limit(chunks: Path, tmp_path: Path):
    encoder = FakeEncoder()
    manifest = embed_chunks(
        chunks, tmp_path / "emb", encoder, passage_prefix="passage: ", limit=5, log=lambda _: None
    )
    assert manifest["counts"]["chunks"] == 5
    assert len(encoder.calls) == 1 and len(encoder.calls[0]) == 5
    assert all(t.startswith("passage: ") for t in encoder.calls[0])
    first = sorted(chunk_texts(chunks))[:5]
    assert sorted(read_vectors(tmp_path / "emb")) == first


def test_wrong_dimension_fails(chunks: Path, tmp_path: Path):
    class Short(FakeEncoder):
        def encode(self, texts):
            return super().encode(texts)[:, :4]

    with pytest.raises(RuntimeError, match="expected"):
        embed_chunks(chunks, tmp_path / "emb", Short(), log=lambda _: None)


def test_out_with_other_files_is_refused_even_with_force(chunks: Path):
    # A typo such as --out data/processed must not write into or delete the chunks.
    for force in (False, True):
        with pytest.raises(ValueError, match="--out must be for embeddings only"):
            embed_chunks(chunks, chunks.parent, FakeEncoder(), force=force, log=lambda _: None)
    assert (chunks / "chunks.parquet").is_file()


def test_missing_chunks_name_the_step(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="run `chunk` first"):
        embed_chunks(tmp_path / "nothing", tmp_path / "emb", FakeEncoder(), log=lambda _: None)


@pytest.mark.parametrize("name", [None, "", "  ", "replace-me"])
def test_model_name_is_required(name):
    with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
        embed.check_model_name(name)


def test_cli_uses_env_model_and_data_dir(chunks: Path, monkeypatch, capsys):
    made = {}

    def fake(name, *, batch_size, device):
        made.update(name=name, batch_size=batch_size, device=device)
        return FakeEncoder(name)

    monkeypatch.setenv("EMBEDDING_MODEL", "fake/from-env")
    monkeypatch.setattr(embed, "SentenceTransformerEncoder", fake)
    data_dir = chunks.parent.parent
    assert main(["--data-dir", str(data_dir), "embed", "--batch-size", "16", "--limit", "3"]) == 0
    assert made == {"name": "fake/from-env", "batch_size": 16, "device": None}
    out = data_dir / "processed" / "embeddings"
    assert json.loads((out / EMBED_MANIFEST).read_text(encoding="utf-8"))["counts"]["chunks"] == 3
    assert "fake/from-env" in capsys.readouterr().out


def test_cli_without_model_fails(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    args = build_parser().parse_args(["--data-dir", str(tmp_path), "embed"])
    with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
        cli.run_embed(args)


@pytest.mark.parametrize("new_api", [True, False])
def test_sentence_transformer_wrapper(monkeypatch, new_api: bool):
    """The wrapper against a stand-in for sentence-transformers (the real one needs a GPU
    notebook and a model download)."""
    import sys
    import types

    seen = {}

    class Model:
        device = "cuda:0"
        max_seq_length = 512

        def __init__(self, name, device=None):
            seen["init"] = (name, device)

        def get_sentence_embedding_dimension(self):
            return DIM

        def encode(self, texts, **kwargs):
            seen["encode"] = kwargs
            return np.stack([vector(t) for t in texts])

    if new_api:
        Model.get_embedding_dimension = Model.get_sentence_embedding_dimension
        del Model.get_sentence_embedding_dimension
    st = types.SimpleNamespace(SentenceTransformer=Model, __version__="9.9")
    torch = types.SimpleNamespace(
        __version__="2.9", cuda=types.SimpleNamespace(get_device_name=lambda i: "Tesla T4")
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    monkeypatch.setitem(sys.modules, "torch", torch)
    encoder = embed.SentenceTransformerEncoder("org/model", batch_size=32, device="cuda")
    assert seen["init"] == ("org/model", "cuda")
    assert encoder.dimension == DIM
    assert encoder.encode(("a", "b")).shape == (2, DIM)
    assert seen["encode"]["batch_size"] == 32
    assert seen["encode"]["normalize_embeddings"] is True
    assert encoder.info()["gpu"] == "Tesla T4"
