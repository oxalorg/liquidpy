import io

def words_to_matrix(words):
	"""
	Convert words to matrix for searching.
	For example:
	```
	['{%', '{%-', '{{'] => [
		{'{': 0},     3 shares, 0 endings
		{'%': 1, '{': 1},
		{'-': 1}
	]
	```
	"""
	matrix = [{} for _ in range(max(len(word) for word in words))]
	for word in words:
		for i, char in enumerate(word):
			matrix[i].setdefault(char, 0)
			if i == len(word) - 1:
				matrix[i][char] += 1
	return matrix

class Stream:

	def __init__(self, stream):
		self.stream = stream
		self.cursor = stream.tell()

	@staticmethod
	def from_file(path):
		return Stream(io.open(path))

	@staticmethod
	def from_string(string):
		return Stream(io.StringIO(string))

	@staticmethod
	def from_stream(stream):
		return Stream(stream)

	def close(self):
		if self.stream:
			self.stream.close()

	def next(self):
		ret = self.stream.read(1)
		self.cursor += 1
		return ret

	def back(self):
		self.cursor -= 1
		self.stream.seek(self.cursor)

	def rewind(self):
		self.stream.seek(0)
		self.cursor = 0

	def eos(self):
		nchar = self.next()
		if not nchar:
			return True
		self.cursor -= 1
		self.stream.seek(self.cursor)
		return False

	def dump(self):
		return self.stream.read()

	def split(self, delimiter, limit = 0, trim = True,
		wraps = ['{}', '[]', '()'], quotes = '"\'`', escape = '\\'):
		preceding, stop = self.until([delimiter], False, wraps, quotes, escape)
		ret = [preceding.strip() if trim else preceding]
		nsplit = 0
		while stop:
			nsplit += 1
			if limit and nsplit >= limit:
				rest = self.dump()
				ret.append(rest.strip() if trim else rest)
				break
			preceding, stop = self.until([delimiter], False, wraps, quotes, escape)
			ret.append(preceding.strip() if trim else preceding)
		return ret

	def until(self, words, greedy = True, wraps = ['{}', '[]', '()'], quotes = '"\'`', escape = '\\'):
		"""
		Get the string until certain words
		For example:
		```
		s = Stream.from_string("abcdefgh")
		s.until(["f", "fg"]) == "abcde", "fg"
		# cursor point to 'h'
		s.until(["f", "fg"], greedy = False) == "abcde", "f"
		# cursor point to 'g'
		s.until(["x", "xy"]) == "abcdefg", ""
		# cursor point to eos
		```
		"""
		ret               = ''
		matrix            = words_to_matrix(words)
		len_matrix        = len(matrix)
		matched_chars     = ''
		matched_candidate = None
		wrap_opens        = {wrap[0]:i for i, wrap in enumerate(wraps)
			if  not any(wrap[0] in mat for mat in matrix) and \
				not any(wrap[1] in mat for mat in matrix)}
		wrap_closes       = {wraps[i][1]:i for wrap_open,i in wrap_opens.items()}
		quote_index       = {quote:i for i, quote in enumerate(quotes)
			if not any(quote in mat for mat in matrix)}
		wrap_flags        = [0 for _ in range(len(wraps))]
		quote_flags       = [False for _ in range(len(quotes))]
		escape_flags      = False
		char              = self.next()
		while True:
			if not char:
				return ret, matched_candidate
			if char == escape:
				escape_flags = not escape_flags
				ret += matched_chars + char
				matched_chars = ''
			elif not escape_flags: # and char != escape
				if char in wrap_opens and not any(quote_flags):
					wrap_flags[wrap_opens[char]] += 1
				elif char in wrap_closes and not any(quote_flags):
					wrap_flags[wrap_closes[char]] -= 1
				elif char in quote_index and \
					not any(flag for i, flag in enumerate(quote_flags) if i != quote_index[char]):
					# make sure I am not quoted
					quote_flags[quote_index[char]] = not quote_flags[quote_index[char]]
				if sum(wrap_flags) > 0 or any(quote_flags):
					ret += matched_chars + char
					matched_chars = ''
				else:
					len_matched_chars = len(matched_chars)
					matching_dict = matrix[len_matched_chars]
					if char in matching_dict:
						matched_chars += char
						endings = matching_dict[char]
						if not greedy and endings:
							return ret, matched_chars
						if endings:
							matched_candidate = matched_chars
							if len_matched_chars + 1 == len_matrix: # we have matched all chars
								return ret, matched_chars

					elif matched_candidate:
						self.back()
						return ret, matched_candidate
					else:
						ret += matched_chars + char
						matched_chars = ''
			else: # char == escape or escape_flags
				escape_flags = False
				ret += matched_chars + char
				matched_chars = ''

			char = self.next()

