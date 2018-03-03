from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from users.models import Doctor, Patient


class CommunicationEntity(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, verbose_name='doctor')
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, verbose_name='patient')
    start = models.DateTimeField('start')
    end = models.DateTimeField('end')

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(CommunicationEntity, self).__init__(*args, **kwargs)
        self.__original_start = self.start
        self.__original_end = self.end

    def clean(self):
        if self.start and self.end:
            start, end = self.start, self.end
            start_changed, end_changed = self.start != self.__original_start, self.end != self.__original_end

            if (start_changed or end_changed) and self.objects.filter(
                    (Q(start__lte=start) & Q(end__gte=start)) |
                    (Q(end__gte=end) & Q(start__lte=end)) |
                    (Q(start__gte=start) & Q(end__lte=end))).exists():
                raise ValidationError(f'{self._meta.model_name} for this time already exists')


class CallEntity(CommunicationEntity):
    pass


class ChatEntity(CommunicationEntity):
    pass


class Chat(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT)


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    text = models.TextField('text')
