class HotWater:
	def __init__(self, id, is_on):
		self._id = id
		self._is_on = is_on

	@property
	def id(self):
		return self._id

	@property
	def is_on(self):
		return self._is_on