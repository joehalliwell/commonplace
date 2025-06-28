from commonplace._utils import truncate, slugify


class TestTruncate:
    def test_truncate_short_text(self):
        result = truncate("Hello", max_length=200)
        assert result == "Hello"

    def test_truncate_long_text(self):
        long_text = "a" * 250
        result = truncate(long_text, max_length=200)
        assert len(result) > 200  # Due to the "more" suffix
        assert result.endswith(" (+50 more)")
        assert result.startswith("a" * 200)

    def test_truncate_exact_length(self):
        text = "a" * 200
        result = truncate(text, max_length=200)
        assert result == text

    def test_truncate_custom_max_length(self):
        result = truncate("Hello world", max_length=5)
        assert result == "Hello (+6 more)"


class TestSlugify:
    def test_slugify_basic(self):
        result = slugify("Hello World")
        assert result == "hello-world"

    def test_slugify_with_special_chars(self):
        result = slugify("Hello, World! & More")
        assert result == "hello-world--more"

    def test_slugify_with_numbers(self):
        result = slugify("Test 123 ABC")
        assert result == "test-123-abc"

    def test_slugify_empty_string(self):
        result = slugify("")
        assert result == ""

    def test_slugify_only_special_chars(self):
        result = slugify("!@#$%^&*()")
        assert result == ""

    def test_slugify_consecutive_spaces(self):
        result = slugify("Hello    World")
        assert result == "hello----world"

    def test_slugify_leading_trailing_spaces(self):
        result = slugify("  Hello World  ")
        assert result == "--hello-world--"
