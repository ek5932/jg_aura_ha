class Gateway():
	def __init__(self, id, name, thermostats):
		self._id = id
		self._name = name
		self._thermostats = thermostats

	@property
	def id(self):
		return self._id

	@property
	def name(self):
		return self._name

	@property
	def thermostats(self):
		return self._thermostats